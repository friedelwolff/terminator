# -*- coding: UTF-8 -*-
#
# Copyright 2011, 2013 Leandro Regueiro
#
# This file is part of Terminator.
#
# Terminator is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# Terminator is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# Terminator. If not, see <http://www.gnu.org/licenses/>.

import itertools
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.admin.models import LogEntry, ADDITION, CHANGE
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, InvalidPage, Paginator
from django.db import transaction, DatabaseError
from django.db.models import Prefetch, Q
from django.db.models import prefetch_related_objects
from django.http import HttpResponse
from django.shortcuts import (get_object_or_404, render, Http404)
from django.template import loader
from django.utils.encoding import force_unicode
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.csrf import csrf_protect
from django.views.generic import DetailView, ListView, TemplateView
from django_comments.models import Comment

from guardian.core import ObjectPermissionChecker
from guardian.shortcuts import get_perms

from terminator.forms import (AdvancedSearchForm, CollaborationRequestForm,
                              ExportForm, ProposalForm, SearchForm,
                              SubscribeForm, ConceptInLanguageForm,
                              ExternalResourceForm)
from terminator.models import *


def terminator_profile_detail(request, username):
    user = get_object_or_404(User, username=username)
    cil_ctype = ContentType.objects.get_for_model(ConceptInLanguage)
    user_comments = Comment.objects.filter(
            user=user,
            content_type=cil_ctype,
            is_public=True,
            is_removed=False,
    ).order_by('-submit_date')
    paginator = Paginator(user_comments, 10)
    # Make sure page request is an int. If not, deliver first page.
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1
    # If page request (9999) is out of range, deliver last page of results.
    try:
        comments = paginator.page(page)
    except (EmptyPage, InvalidPage):
        comments = paginator.page(paginator.num_pages)
    prefetch_related_objects(comments.object_list,
            'content_object__language',
            'content_object__concept',
            'content_object__concept__glossary',
    )
    glossary_list = list(Glossary.objects.all())
    user_glossaries = []
    checker = ObjectPermissionChecker(user)
    checker.prefetch_perms(glossary_list)
    for glossary in glossary_list:
        if checker.has_perm('is_owner_for_this_glossary', glossary):
            user_glossaries.append({'glossary': glossary, 'role': _(u"Owner")})
        elif checker.has_perm('is_lexicographer_in_this_glossary', glossary):
            user_glossaries.append({'glossary': glossary, 'role': _(u"Lexicographer")})
        elif checker.has_perm('is_terminologist_in_this_glossary', glossary):
            user_glossaries.append({'glossary': glossary, 'role': _(u"Terminologist")})

    translation_ctype = ContentType.objects.get_for_model(Translation)
    translation_changes = recent_translation_changes(LogEntry.objects.filter(
                content_type=translation_ctype,
                user=user,
            ).order_by("-action_time")[:10])


    context = {
        'thisuser': user,
        'glossaries': user_glossaries,
        'comments': comments,
        'search_form': SearchForm(),
        'next': request.get_full_path(),
        'translation_changes': translation_changes,
    }
    return render(request, "profiles/profile_detail.html", context)


class ProfileListView(ListView):
    def get_queryset(self):
        qs = super(ProfileListView, self).get_queryset()
        return qs.exclude(username="AnonymousUser")

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(ProfileListView, self).get_context_data(**kwargs)
        # Add the breadcrumbs search form to context
        context['search_form'] = SearchForm()
        # Add the request path to correctly render the "log in" or "log out"
        # link in template.
        context['next'] = self.request.get_full_path()
        return context


class TerminatorDetailView(DetailView):
    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(TerminatorDetailView, self).get_context_data(**kwargs)
        # Add the breadcrumbs search form to context
        context['search_form'] = SearchForm()
        # Add the request path to correctly render the "log in" or "log out"
        # link in template.
        context['next'] = self.request.get_full_path()
        return context


class TerminatorListView(ListView):
    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(TerminatorListView, self).get_context_data(**kwargs)
        # Add the breadcrumbs search form to context
        context['search_form'] = SearchForm()
        # Add the request path to correctly render the "log in" or "log out"
        # link in template.
        context['next'] = self.request.get_full_path()
        return context


class TerminatorTemplateView(TemplateView):
    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(TerminatorTemplateView, self).get_context_data(**kwargs)
        # Add the breadcrumbs search form to context
        context['search_form'] = SearchForm()
        # Add the request path to correctly render the "log in" or "log out"
        # link in template.
        context['next'] = self.request.get_full_path()
        return context


class ConceptView(TerminatorDetailView):

    # no language

    def get_queryset(self):
        qs = super(ConceptView, self).get_queryset()
        return qs.select_related('glossary')

    def get_template_names(self):
        return "terminator/concept.html"

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = ExternalResourceForm(request.POST)
        if form.is_valid():
            resource = form.save(commit=False)
            resource.concept = self.object
            resource.save()
            LogEntry.objects.log_action(
                user_id=self.request.user.pk,
                content_type_id=ContentType.objects.get_for_model(self.object).pk,
                object_id=self.object.pk,
                object_repr=force_unicode(self.object),
                action_flag=CHANGE,
            )
            form = ExternalResourceForm()

        context = self.get_context_data(object=self.object)
        context["form"] = form
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(ConceptView, self).get_context_data(**kwargs)
        form = ExternalResourceForm()
        context['form'] = form
        context['source_language_finalized'] = self.object.source_language_finalized()
        # Limit to pre-approved list of languages for this glossary?
        context['available_languages'] = Language.objects.order_by("pk")
        context['external_resources'] = ExternalResource.objects.filter(
                concept=self.object,
                language_id=None,
        )
        return context


class ConceptDetailView(TerminatorDetailView):
    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(ConceptDetailView, self).get_context_data(**kwargs)
        context['available_languages'] = Language.objects.order_by("pk")
        try:
            language = Language.objects.get(pk=self.kwargs.get('lang'))
        except Language.DoesNotExist:
            raise Http404
        context['current_language'] = language
        context['translations'] = context['concept'].translation_set.filter(
                language=language)
        context['comments_thread'], created = ConceptInLanguage.objects.get_or_create(
                concept=context['concept'],
                language=language,
        )

        summary_message = None
        finalized = False
        try:
            if not created:
                summary_message = SummaryMessage.objects.get(
                        concept=context['concept'],
                        language=language,
                )
                finalized = summary_message.is_finalized
        except SummaryMessage.DoesNotExist:
            pass
        context['summary_message'] = summary_message
        context['finalized'] = finalized

        return context


class ConceptSourceView(TerminatorDetailView):

    def get_queryset(self):
        qs = super(ConceptSourceView, self).get_queryset()
        return qs.select_related('glossary', 'glossary__source_language')

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_template_names(self):
        return "terminator/concept_source.html"

    def get_context_data(self, **kwargs):
        context = super(ConceptSourceView, self).get_context_data(**kwargs)
        concept = context['concept']
        language = concept.glossary.source_language
        translations = Translation.objects.filter(concept=concept, language=language)
        initial = {}
        try:
            definition = Definition.objects.filter(
                    concept=concept,
                    language=language,
            ).latest()
        except Definition.DoesNotExist:
            definition = None
        may_edit = False
        message = ""
        message_class = ""
        user = self.request.user
        glossary_perms = get_perms(user, concept.glossary)
        if user.is_authenticated:
            if 'is_lexicographer_in_this_glossary' in glossary_perms or \
                    ('is_terminologist_in_this_glossary' in glossary_perms and \
                    not concept.source_language_finalized()):
                may_edit = True
        if self.request.method == 'POST':
            if not may_edit:
                raise PermissionDenied
            if definition:
                initial["definition"] = definition.definition_text
            form = ConceptInLanguageForm(self.request.POST, initial=initial)
            if form.is_valid() and form.has_changed():
                cleaned_data = form.cleaned_data
                for name in form.changed_data:
                    value = cleaned_data.get(name)
                    if not value:
                        # no use in somebody setting the empty string
                        continue
                    # assume it is either "translation" or "definition"
                    if name == "translation":
                        if value in (t.translation_text for t in translations):
                            message = _("This term is already present.")
                            message_class = "errornote"
                            break
                        model = Translation(translation_text=value)
                        translations = Translation.objects.filter(concept=concept, language=language)
                        # model is not saved yet, but the queryset will only
                        # load later in the template.
                    elif name == "definition":
                        if definition:
                            definition.is_finalized = False
                            definition.save()
                        model = Definition(definition_text=value)
                        definition = model
                        # consider: definition.is_finalized = True
                    model.language = language
                    model.concept = concept
                    model.save()
                    # Log the addition using LogEntry from admin contrib app
                    LogEntry.objects.log_action(
                        user_id=self.request.user.pk,
                        content_type_id=ContentType.objects.get_for_model(model).pk,
                        object_id=model.pk,
                        object_repr=force_unicode(model),
                        action_flag=ADDITION,
                    )
                    message = _("Your contribution was saved: %s") % value
                    message_class = "successnote"

        context['glossary_perms'] = glossary_perms
        context['may_edit'] = may_edit
        context['message'] = message
        context['message_class'] = message_class
        context['current_language'] = language
        translations = translations.select_related('administrative_status')
        translations = sorted(translations, key=lambda t: t.cmp_key())
        context['translations'] = translations
        context['definition'] = definition
        context['comments_thread'], _c = ConceptInLanguage.objects.get_or_create(
                concept=concept,
                language=language,
        )
        if definition:
            initial["definition"] = definition.definition_text
        form = ConceptInLanguageForm(initial=initial)

        # Customise fields a bit to suit permissions and workflow
        if not may_edit and definition:
                form.fields['definition'].disabled = True
        elif definition and definition.is_finalized:
            form.fields['definition'].disabled = True

        context['form'] = form
        return context


class GlossaryDetailView(TerminatorDetailView):
    def post(self, request, *args, **kwargs):
        if not settings.FEATURES.get('collaboration', True) and \
           not settings.FEATURES.get('subscription', True):
            raise PermissionDenied
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        # Call the base implementation first to get a context
        context = super(GlossaryDetailView, self).get_context_data(**kwargs)
        subscribe_form = None
        collaboration_form = None
        # Add the collaboration request form to context and treat it if form
        # data is received.
        if self.request.method == 'POST':
            if 'collaboration_role' in self.request.POST:
                collaboration_form = CollaborationRequestForm(self.request.POST)
                if collaboration_form.is_valid():
                    try:
                        with transaction.atomic():
                            collaboration_request = collaboration_form.save(commit=False)
                            collaboration_request.user = self.request.user
                            collaboration_request.for_glossary = self.object
                            collaboration_request.save()
                            #TODO notify the glossary owners by email that a new
                            # collaboration request is awaiting to be considered.
                            # Maybe do this in the save() method in the model.
                            message = _("You will receive a message when the "
                                        "glossary owners have considerated your "
                                        "request.")
                            context['collaboration_request_message'] = message
                            collaboration_form = CollaborationRequestForm()
                    except DatabaseError:
                        # Postgres raises DatabaseError instead of IntegrityError :-(
                        error_message = _("You already sent a similar request "
                                          "for this glossary!")
                        context['collaboration_request_error_message'] = error_message
                        #TODO consider updating the request DateTimeField to
                        # now and then save.
            elif 'subscribe_to_this_glossary' in self.request.POST:
                subscribe_form = SubscribeForm(self.request.POST)
                if subscribe_form.is_valid():
                    self.object.subscribers.add(self.request.user)
                    context['subscribe_message'] = _("You have subscribed to "
                                                     "get email notifications "
                                                     "when a comment is made.")
                    subscribe_form = SubscribeForm()
        subscribe_form = subscribe_form or SubscribeForm()
        collaboration_form = collaboration_form or CollaborationRequestForm()
        context['subscribe_form'] = subscribe_form
        context['collaboration_request_form'] = collaboration_form

        cil_ctype = ContentType.objects.get_for_model(ConceptInLanguage)
        context.update({
            'latest_comments': Comment.objects.order_by("-id").
                # the cil_ctype filter should be unnecessary, but will become
                # required if we ever have comments on other content types.
                filter(
                    content_type=cil_ctype,
                    is_public=True,
                    is_removed=False,
                    #the __integer transform changes the str object_pk into an
                    #INT that can be joined by the database
                    object_pk__integer__in=ConceptInLanguage.objects.filter(
                        concept__glossary=self.object,
                    ),
                ).
                select_related("user").
                prefetch_related("content_object", "content_object__concept")[:5],
        })
        return context


class GlossaryConceptsView(LoginRequiredMixin, TerminatorDetailView):
    def get_template_names(self):
        return "terminator/glossary_concepts.html"


@csrf_protect
def terminator_index(request):
    new_proposal_message = ""
    if request.method == 'POST':
        proposal_form = ProposalForm(request.POST)
        if proposal_form.is_valid():
            new_proposal = proposal_form.save(commit=False)
            new_proposal.user = request.user
            new_proposal.save()
            #TODO send a mail or notify in any way to the glossary owners in
            # order to get them manage the proposal. Maybe do this in the
            # save() method in the model.

            # Log the addition using LogEntry from admin contrib app
            LogEntry.objects.log_action(
                user_id = request.user.pk,
                content_type_id = ContentType.objects.get_for_model(new_proposal).pk,
                object_id = new_proposal.pk,
                object_repr = force_unicode(new_proposal),
                action_flag = ADDITION
            )
            new_proposal_message = _("Thank you for sending a new proposal. "
                                     "You may send more!")
            proposal_form = ProposalForm()
    else:
        proposal_form = ProposalForm()

    glossary_ctype = ContentType.objects.get_for_model(Glossary)
    concept_ctype = ContentType.objects.get_for_model(Concept)
    cil_ctype = ContentType.objects.get_for_model(ConceptInLanguage)
    translation_ctype = ContentType.objects.get_for_model(Translation)

    translation_changes = LogEntry.objects.filter(
            content_type=translation_ctype,
    ).order_by("-action_time")[:8]

    context = {
        'search_form': SearchForm(),
        'proposal_form': proposal_form,
        'new_proposal_message': new_proposal_message,
        'next': request.get_full_path(),
        'glossaries': Glossary.objects.all(),
        'latest_proposals': Proposal.objects.order_by("-id").
                select_related("language", "for_glossary")[:8],
        'latest_comments': Comment.objects.order_by("-id").
                # this filter should be unnecessary, but will become required
                # if we ever have comments on other content types.
                filter(
                    content_type=cil_ctype,
                    is_public=True,
                    is_removed=False,
                ).
                select_related("user").
                prefetch_related("content_object", "content_object__concept")[:8],
        'latest_glossary_changes': LogEntry.objects.filter(content_type=glossary_ctype).order_by("-action_time")[:8],
        'latest_concept_changes': LogEntry.objects.filter(content_type=concept_ctype).order_by("-action_time")[:8],
        'latest_translation_changes': recent_translation_changes(translation_changes),
    }

    return render(request, 'index.html', context)


def export_glossaries_to_TBX(glossaries, desired_languages=None, export_all_definitions=False, export_terms="all"):
    if desired_languages is None:
        desired_languages = []
    if not glossaries:
        raise Http404
    elif len(glossaries) == 1:
        glossary_data = glossaries[0]
    else:
        glossary_description = _("TBX file created by exporting the following "
                                 "glossaries: ")
        glossaries_names_list = []
        for gloss in glossaries:
            glossaries_names_list.append(gloss.name)
        glossary_description += ", ".join(glossaries_names_list)
        glossary_data = {
            "name": _("Terminator TBX exported glossary"),
            "description": glossary_description,
        }
    data = {
        'glossary': glossary_data,
        'concepts': [],
    }

    preferred = AdministrativeStatus.objects.get(name="Preferred")
    admitted = AdministrativeStatus.objects.get(name="Admitted")
    not_recommended = AdministrativeStatus.objects.get(name="Not recommended")

    concept_qs = Concept.objects.filter(glossary__in=glossaries).order_by("glossary", "id")

    #Give template an indication of whether any related concepts are used:
    data["use_related_concepts"] = Concept.objects.filter(
            related_concepts__id__in=concept_qs,
    ).exists()

    translation_filter = Q()
    if export_terms == 'preferred':
        translation_filter |= Q(administrative_status=preferred)
    elif export_terms == 'preferred+admitted':
        translation_filter |= Q(administrative_status=preferred)
        translation_filter |= Q(administrative_status=admitted)
    elif export_terms == 'preferred+admitted+not_recommended':
        translation_filter |= Q(administrative_status__in=(preferred, admitted, not_recommended))

    # Only the finished summary messages are exported
    summary_filter = Q(is_finalized=True)
    definition_filter = Q()
    if not export_all_definitions:
        definition_filter &= Q(is_finalized=True)

    # Assume that there is at least a term or a definition for a used language.
    glossary_filter = Q(concept__glossary__in=glossaries)
    translations = Translation.objects.filter(glossary_filter & translation_filter)
    definitions = Definition.objects.filter(glossary_filter & definition_filter)
    used_languages = set(translations.values_list('language', flat=True).distinct())
    used_languages.update(definitions.values_list('language', flat=True).distinct())
    used_languages.difference_update(set(desired_languages))
    used_languages = sorted(used_languages)

    def key_func(obj):
        return (obj.concept_id, obj.language_id)

    def query_lookup_dict(qs):
        results = {}
        for key, group in itertools.groupby(qs, key_func):
            results[key] = list(group)
        return results

    translations = translations.select_related(
            'part_of_speech',
            'grammatical_number',
            'grammatical_gender',
            'administrative_status',
            'administrative_status_reason',
    )
    if "sqlite" in settings.DATABASES['default']['ENGINE']:
        # SQLite can't handle more than 999 translations (by default). We do it
        # in batches so that testing with SQLite is still possible.
        bool(translations)
        for i in range(0, len(translations), 999):
            prefetch_related_objects(translations[i:i+999], "corpusexample_set", "contextsentence_set")
    else:
        translations = translations.prefetch_related("corpusexample_set", "contextsentence_set")

    tr_dict = query_lookup_dict(translations)
    def_dict = query_lookup_dict(definitions)

    resources = ExternalResource.objects.filter(glossary_filter)
    resource_dict = query_lookup_dict(resources)

    summaries = SummaryMessage.objects.filter(glossary_filter & summary_filter)
    summary_dict = query_lookup_dict(summaries)


    def generate_concepts():
        #generator so that we don't keep things in memory
        for concept in concept_qs.iterator():
            concept_data = {'concept': concept, 'languages': []}

            for language_code in used_languages:
                key = (concept.id, language_code)

                lang_translations = tr_dict.get(key, [])
                lang_resources = resource_dict.get(key, [])

                lang_summary_message = summary_dict.get(key, None)
                if lang_summary_message:
                    assert len(lang_summary_message) == 1
                    lang_summary_message = lang_summary_message[0].text

                # Get the last definition by id
                #python 3:
                #lang_definition = max(def_dict.get(key, []), None, lambda x: x.id)
                #python 2:
                lang_definition = None
                lang_definitions = def_dict.get(key, None)
                if lang_definitions:
                    lang_definition = max(lang_definitions, key=lambda x: x.id)

                if not any((lang_translations, lang_resources, lang_definition, lang_summary_message)):
                    # no real content
                    continue

                lang_data = {
                    'iso_code': language_code,
                    'translations': lang_translations,
                    'externalresources': lang_resources,
                    'definition': lang_definition,
                    'summarymessage': lang_summary_message,
                }
                concept_data['languages'].append(lang_data)
            if concept_data['languages']:
                yield concept_data

    data['concepts'] = generate_concepts()

    #TODO:
    # Raise Http404 if there are no concepts in the resulting glossary
    #if not data['concepts']:
    #    raise Http404
    # Important enough? Can't easily do with generator.

    # Create the HttpResponse object with the appropriate header.
    response = HttpResponse(content_type='application/x-tbx')
    if len(glossaries) == 1:
        from urllib import quote
        encoded_name = "%s%s" % (quote(glossaries[0].name.encode('utf-8')), '.tbx')
        response['Content-Disposition'] = "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (encoded_name, encoded_name)
        # http://test.greenbytes.de/tech/tc2231/
        # The encoding of filename is wrong, but seems like it will trigger the
        # right bugs in older browsers that don't support filename* to actually
        # display the right filename.
    else:
        response['Content-Disposition'] = 'attachment; filename=terminator_several_exported_glossaries.tbx'

    # Create the response
    t = loader.get_template('export.tbx')
    response.write(t.render({'data': data}))
    return response


def autoterm(request, language_code):
    #TODO Make this view to export for any language pair and not only for
    # english and another language.
    language = get_object_or_404(Language, pk=language_code)
    english = get_object_or_404(Language, pk="en")
    glossaries = list(Glossary.objects.all())
    if not glossaries:
        raise Http404
    return export_glossaries_to_TBX(glossaries, [language, english])


@csrf_protect
@login_required
def export(request):
    #exporting_message = ""#TODO show export confirmation message
    if request.method == 'GET' and 'from_glossaries' in request.GET:
        export_form = ExportForm(request.GET)
    elif request.method == 'POST' and 'from_glossaries' in request.POST:
        export_form = ExportForm(request.POST)
        if export_form.is_valid():
            glossaries = export_form.cleaned_data['from_glossaries']
            desired_languages = export_form.cleaned_data['for_languages']
            export_all_definitions = export_form.cleaned_data['export_not_finalized_definitions']
            export_terms = export_form.cleaned_data['export_terms']
            #exporting_message = "Exported succesfully."#TODO show export confirmation message
            return export_glossaries_to_TBX(glossaries, desired_languages,
                                            export_all_definitions,
                                            export_terms)
    else:
        export_form = ExportForm()
    context = {
        'search_form': SearchForm(),
        'export_form': export_form,
        #'exporting_message': exporting_message,#TODO show export confirmation message
        'next': request.get_full_path(),
    }
    return render(request, 'export.html', context)


def search(request):
    search_results = None
    if request.method == 'GET' and 'search_string' in request.GET:
        if "advanced" in request.path:
            search_form = AdvancedSearchForm(request.GET)
        else:
            search_form = SearchForm(request.GET)

        if search_form.is_valid():
            search_results = []
            if "advanced" in request.path:
                queryset = Translation.objects.all()
                if search_form.cleaned_data['filter_by_glossary']:
                    queryset = queryset.filter(concept__glossary=search_form.cleaned_data['filter_by_glossary'])

                if search_form.cleaned_data['filter_by_language']:
                    queryset = queryset.filter(language=search_form.cleaned_data['filter_by_language'])

                #TODO add filter by process status

                if search_form.cleaned_data['filter_by_part_of_speech']:
                    queryset = queryset.filter(part_of_speech=search_form.cleaned_data['filter_by_part_of_speech'])

                if search_form.cleaned_data['filter_by_administrative_status']:
                    queryset = queryset.filter(administrative_status=search_form.cleaned_data['filter_by_administrative_status'])

                if search_form.cleaned_data['also_show_partial_matches']:
                    queryset = queryset.filter(translation_text__icontains=search_form.cleaned_data['search_string'])
                else:
                    queryset = queryset.filter(translation_text__iexact=search_form.cleaned_data['search_string'])
            else:
                queryset = Translation.objects.filter(translation_text__iexact=search_form.cleaned_data['search_string'])

            # Limit for better worst-case performance. Consider pager.
            limit = 20
            if request.user.is_authenticated:
                limit = 100
            queryset = queryset.select_related('concept', 'concept__glossary', 'administrative_status')[:limit]
            queryset = queryset.prefetch_related(Prefetch('concept__translation_set', to_attr="others"))

            previous_concept = None
            for trans in queryset:# All recovered translations are ordered by concept and then by language
                try:
                    definition = Definition.objects.filter(concept_id=trans.concept_id, language_id=trans.language_id).latest()
                except Definition.DoesNotExist:
                    definition = None

                # If this is the first translation for this concept
                if previous_concept != trans.concept_id:
                    is_first = True
                    previous_concept = trans.concept_id
                    other_translations = itertools.islice((c for c in trans.concept.others if c.pk != trans.pk), 7)
                else:
                    other_translations = None
                    is_first = False

                search_results.append({
                    "translation": trans,
                    "definition": definition,
                    "other_translations": other_translations,
                    "is_first": is_first,
                })
    elif "advanced" in request.path:
        search_form = AdvancedSearchForm()
    else:
        search_form = SearchForm()

    context = {
        'search_form': search_form,
        'search_results': search_results,
        'next': request.get_full_path(),
    }

    template_name = 'search.html'
    if "advanced" in request.path:
        template_name = 'advanced_search.html'

    return render(request, template_name, context)