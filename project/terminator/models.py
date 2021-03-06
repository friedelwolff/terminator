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

from __future__ import unicode_literals

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import Field, Transform
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.encoding import force_text, python_2_unicode_compatible
from django.utils.html import format_html, mark_safe
from django.utils.translation import ugettext_lazy as _

from guardian.shortcuts import assign_perm, get_users_with_perms
from simple_history.models import HistoricalRecords

import itertools
import re

@python_2_unicode_compatible
class PartOfSpeech(models.Model):
    name = models.CharField(max_length=50, verbose_name=_("name"))
    tbx_representation = models.CharField(max_length=100, verbose_name=_("TBX representation"))
    description = models.TextField(blank=True, verbose_name=_("description"))

    class Meta:
        verbose_name = _("part of speech")
        verbose_name_plural = _("parts of speech")

    def __str__(self):
        return self.name

    def allows_grammatical_gender_for_language(self, language):
        try:
            response = self.partofspeechforlanguage_set.get(language=language).allows_grammatical_gender
        except ObjectDoesNotExist:
            response = False
        return response

    def allows_grammatical_number_for_language(self, language):
        try:
            response = self.partofspeechforlanguage_set.get(language=language).allows_grammatical_number
        except ObjectDoesNotExist:
            response = False
        return response


@python_2_unicode_compatible
class GrammaticalGender(models.Model):
    name = models.CharField(max_length=50, verbose_name=_("name"))
    tbx_representation = models.CharField(max_length=100, verbose_name=_("TBX representation"))
    description = models.TextField(blank=True, verbose_name=_("description"))

    class Meta:
        verbose_name = _("grammatical gender")
        verbose_name_plural = _("grammatical genders")

    def __str__(self):
        return self.name


@python_2_unicode_compatible
class GrammaticalNumber(models.Model):
    name = models.CharField(max_length=50, verbose_name=_("name"))
    tbx_representation = models.CharField(max_length=100, verbose_name=_("TBX representation"))
    description = models.TextField(blank=True, verbose_name=_("description"))

    class Meta:
        verbose_name = _("grammatical number")
        verbose_name_plural = _("grammatical numbers")

    def __str__(self):
        return self.name


@python_2_unicode_compatible
class Language(models.Model):
    iso_code = models.CharField(primary_key=True, max_length=10, verbose_name=_("ISO code"))
    name = models.CharField(max_length=50, verbose_name=_("name"))
    description = models.TextField(verbose_name=_("description"), null=True, blank=True)
    parts_of_speech = models.ManyToManyField(PartOfSpeech, through='PartOfSpeechForLanguage', verbose_name=_("parts of speech"))
    grammatical_genders = models.ManyToManyField(GrammaticalGender, blank=True, verbose_name=_("grammatical genders"))
    grammatical_numbers = models.ManyToManyField(GrammaticalNumber, blank=True, verbose_name=_("grammatical numbers"))

    class Meta:
        verbose_name = _("language")
        verbose_name_plural = _("languages")

    def __str__(self):
        return _("%(language_name)s (%(iso_code)s)") % {'language_name': self.name, 'iso_code': self.iso_code}

    def allows_part_of_speech(self, part_of_speech):
        return part_of_speech in self.parts_of_speech.all()

    def allows_grammatical_gender(self, grammatical_gender):
        return grammatical_gender in self.grammatical_genders.all()

    def allows_grammatical_number(self, grammatical_number):
        return grammatical_number in self.grammatical_numbers.all()

    def allows_administrative_status_reason(self, administrative_status_reason):
        return administrative_status_reason in self.administrativestatusreason_set.all()


@python_2_unicode_compatible
class PartOfSpeechForLanguage(models.Model):
    language = models.ForeignKey(Language, on_delete=models.CASCADE, verbose_name=_("language"))
    part_of_speech = models.ForeignKey(PartOfSpeech, on_delete=models.CASCADE, verbose_name=_("part of speech"))
    allows_grammatical_gender = models.BooleanField(default=False, verbose_name=_("allows grammatical gender"))
    allows_grammatical_number = models.BooleanField(default=False, verbose_name=_("allows grammatical number"))

    class Meta:
        verbose_name_plural = _("parts of speech for languages")
        unique_together = ("language", "part_of_speech")

    def __str__(self):
        return _("%(part_of_speech)s (%(language)s)") % {'part_of_speech': self.part_of_speech, 'language': self.language_id}


@python_2_unicode_compatible
class AdministrativeStatus(models.Model):
    name = models.CharField(max_length=20, verbose_name=_("name"))
    tbx_representation = models.CharField(primary_key=True, max_length=25, verbose_name=_("TBX representation"))
    description = models.TextField(blank=True, verbose_name=_("description"))
    allows_reason = models.BooleanField(default=False, verbose_name=_("allows setting administrative status reason"))

    class Meta:
        verbose_name = _("administrative status")
        verbose_name_plural = _("administrative statuses")

    def __str__(self):
        return self.name

@python_2_unicode_compatible
class AdministrativeStatusReason(models.Model):
    languages = models.ManyToManyField(Language, verbose_name=_("languages"))
    name = models.CharField(max_length=40, verbose_name=_("name"))
    description = models.TextField(verbose_name=_("description"))

    class Meta:
        verbose_name = _("administrative status reason")
        verbose_name_plural = _("administrative status reasons")

    def __str__(self):
        return self.name


@python_2_unicode_compatible
class ExternalLinkType(models.Model):
    name = models.CharField(max_length=50, verbose_name=_("name"))
    tbx_representation = models.CharField(primary_key=True, max_length=30, verbose_name=_("TBX representation"))
    description = models.TextField(verbose_name=_("description"))

    class Meta:
        verbose_name = _("external link type")
        verbose_name_plural = _("external link types")

    def __str__(self):
        return self.name


@python_2_unicode_compatible
class Glossary(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name=_("name"))
    description = models.TextField(verbose_name=_("description"))
    source_language = models.ForeignKey(Language, related_name='+', on_delete=models.PROTECT, default='en', verbose_name=_("source language"))
    other_languages = models.ManyToManyField(Language, blank=True, related_name='+', verbose_name=_("other languages"))
    subscribers = models.ManyToManyField(User, blank=True, verbose_name=_("subscribers"))
    #main_language #TODO this should be the main language of the glossary. This language is used when exporting the glossary and is also the language in which the glossary name and description are written.
    #accepted_languages #TODO this should be a list of languages that can be used in the glossary. If this is finally used should be restricted for translations, definitions, external resources, proposals, ConceptInLanguage,... in the Glossary.
    #TODO In the subject_fields field, when trying to remove a concept from the
    # subject_fields of a Glossary make sure before that it is not used as
    # subject field for any of the Glossary concepts.
    #TODO In the subject_fields field, see if is an option using
    # limit_choices_to = {'glossary__exact': self} in order to reduce the
    # options shown in the admin site.
    subject_fields = models.ManyToManyField('Concept', related_name='glossary_subject_fields', blank=True, verbose_name=_("subject fields"))

    class Meta:
        verbose_name = _("glossary")
        verbose_name_plural = _("glossaries")
        permissions = (
            ('specialist', 'Specialist for this glossary'),
            ('terminologist', 'Terminologist for this glossary'),
            ('owner', 'Owner of this glossary'),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('terminator_glossary_detail', kwargs={'pk': self.pk})

    def assign_specialist_permissions(self, user):
        assign_perm('specialist', user, self)

    def assign_terminologist_permissions(self, user):
        assign_perm('terminologist', user, self)

    def assign_owner_permissions(self, user):
        assign_perm('owner', user, self)

    def get_collaborators(self):
        from guardian.models import UserObjectPermission
        # This is what we want:
        # user_dict = get_users_with_perms(self, attach_perms=True, with_superusers=True)
        # for user, perms in user_dict: if 'xxx' in perms: ...
        # XXX: attach_perms=True makes this very slow with lots of users
        # https://github.com/django-guardian/django-guardian/issues/494
        # We could limit the damage by first checking if there is a reasonable
        # number of users and adapt the UI, but it sucks to have to make the
        # choice.

        # Hand-written for constant number of queries. This is not exactly
        # equivalent, since we are not checking group permissions.
        glossary_ctype = ContentType.objects.get_for_model(Glossary)
        collaborators = []
        listed_users = set()
        for user in User.objects.filter(is_superuser=True, is_active=True):
            listed_users.add(user)
            collaborators.append({'user': user, 'role': _("administrator")})
        for role, codename in (
                (_("owner"), "owner"),
                (_("terminologist"), "terminologist"),
                (_("specialist"), "specialist")):
            permission_lines = UserObjectPermission.objects.filter(
                    permission__codename=codename,
                    content_type=glossary_ctype,
                    object_pk=self.id,
            ).order_by("user__username").select_related("user")
            for line in permission_lines:
                if line.user not in listed_users:
                    # We don't want user xxx as admin and owner and ...
                    listed_users.add(line.user)
                    collaborators.append({'user': line.user, 'role': role})
        return collaborators

    def get_recent_changes(self):
        qs = LogEntry.objects.none()
        for Model in (Translation, Definition, ExternalResource, ConceptInLanguage):
            ctype = ContentType.objects.get_for_model(Model)
            qs = qs.union(LogEntry.objects.filter(
                content_type=ctype,
                object_id__integer__in=Model.objects.filter(
                    concept__glossary=self,
                ),
            ).order_by())
        return process_recent_changes(qs.order_by("-action_time")[:5])

@python_2_unicode_compatible
class Concept(models.Model):
    glossary = models.ForeignKey(Glossary, on_delete=models.CASCADE, verbose_name=_("glossary"))
    subject_field = models.ForeignKey('self', related_name='concepts_in_subject_field', null=True, blank=True, on_delete=models.PROTECT, verbose_name=_("subject field"))
    broader_concept = models.ForeignKey('self', related_name='narrower_concepts', null=True, blank=True, on_delete=models.PROTECT, verbose_name=_("broader concept"))
    related_concepts = models.ManyToManyField('self', blank=True, verbose_name=_("related concepts"))
    # This keeps a readable version cached in this table so that no joining
    # with Translation is required for a human readable form.
    repr_cache = models.CharField(max_length=200, editable=False, null=True, blank=True, verbose_name=_("representation"))

    class Meta:
        verbose_name = _("concept")
        verbose_name_plural = _("concepts")
        ordering = ['id']

    def __str__(self):
        if self.repr_cache:
            return self.repr_cache
        return _("Concept #%(concept_id)d") % {'concept_id': self.id}

    def update_repr_cache(self):
        if not self.id:
            # can happen in test teardown and similar situations
            return
        src_translations = self.translation_set.filter(
                language_id=self.glossary.source_language_id,
        )
        repr_ = self.repr_from(src_translations)
        if repr_:
            self.repr_cache = repr_
            self.save(update_fields=['repr_cache'])

    def repr_from(self, translations):
        translations = sorted(translations, key=lambda t: t.cmp_key())
        repr_ = ', '.join(t.translation_text for t in translations[:4])[:200]
        repr_ = "#%d: %s" % (self.id, repr_)
        return repr_

    def source_language_finalized(self):
        return ConceptInLanguage.objects.filter(
                    concept=self,
                    language=self.glossary.source_language_id,
                    is_finalized=True,
        ).exists()

    def prev_concept(self):
        """The previous concept in the same glossary."""
        return Concept.objects.filter(
                glossary=self.glossary,
                id__lt=self.id,
        ).only("id", "repr_cache").order_by('-id').first()

    def next_concept(self):
        """The next concept in the same glossary."""
        return Concept.objects.filter(
                glossary=self.glossary,
                id__gt=self.id,
        ).only("id", "repr_cache").order_by('id').first()

    def other_concepts(self):
        """Some surrounding concepts in the glossary."""
        previous_concepts = Concept.objects.filter(
                glossary=self.glossary,
                id__lt=self.pk,
        ).only("id", "repr_cache").order_by('-id')[:5]
        next_concepts = Concept.objects.filter(
                glossary=self.glossary,
                id__gte=self.pk,
        ).only("id", "repr_cache").order_by('id')[:6]

        return itertools.chain(reversed(previous_concepts), next_concepts)

    def get_absolute_url(self):
        return reverse('terminator_concept_detail', kwargs={'pk': self.pk})


def update_repr_cache(sender, **kwargs):
    translation = kwargs.get('instance')
    translation.concept.update_repr_cache()
post_delete.connect(update_repr_cache, sender='terminator.Translation')


class ConceptLangUrlMixin(object):
    def get_absolute_url(self):
        if self.concept.glossary.source_language_id == self.language_id:
            return reverse("terminator_concept_source", kwargs={'pk': self.concept.pk})
        return reverse('terminator_concept_detail_for_language', kwargs={'pk': self.concept.pk, 'lang': self.language.pk})


@python_2_unicode_compatible
class ConceptInLanguage(models.Model, ConceptLangUrlMixin):
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE)
    language = models.ForeignKey(Language, on_delete=models.PROTECT)
    summary = models.TextField(blank=True, verbose_name=_("summary message"))
    is_finalized = models.BooleanField(default=False, verbose_name=_("is finalized"))
    date = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("concept", "language")

    def definition(self):
        try:
            return Definition.objects.get(concept=self.concept_id, language=self.language_id)
        except Definition.DoesNotExist:
            return None

    def external_resources(self):
        return ExternalResource.objects.filter(concept=self.concept_id, language=self.language_id)

    def other_language_data(self):
        """Information on the (other) target languages"""
        terms = Translation.objects.filter(concept=self.concept_id).exclude(
                language=self.language_id,
        ).select_related('administrative_status', 'language')

        def cmp(t):
            return t.language_id, t.cmp_key()
        terms = sorted(terms, key=cmp)

        languages = {}
        for lang, terms in itertools.groupby(terms, lambda t: t.language_id):
            languages[lang] = {"terms": list(terms)}

        definitions = Definition.objects.filter(concept=self.concept_id).exclude(
                language=self.language_id,
        )
        for definition in definitions:
            lang = definition.language_id
            if lang not in languages:
                languages[lang] = {}
            languages[lang]["definition"] = definition

        return languages

    def related_concepts_data(self):
        """Information on related concepts in the same language."""
        concept_qs = Concept.objects.filter(
                id__in=self.concept.related_concepts.all(),
        ).order_by().union(Concept.objects.filter(
                id__in=self.concept.narrower_concepts.all(),
        ).order_by())
        if self.concept.broader_concept_id:
            concept_qs = concept_qs.union(Concept.objects.filter(
                id=self.concept.broader_concept_id,
        ).order_by())

        terms = Translation.objects.filter(
            concept__in=concept_qs,
            language=self.language_id,
        ).select_related('administrative_status', 'language').order_by()

        def cmp(t):
            return t.concept_id, t.cmp_key()
        terms = sorted(terms, key=cmp)

        concepts = {}
        for concept, terms in itertools.groupby(terms, lambda t: t.concept_id):
            concepts[concept] = {"terms": list(terms)}

        definitions = Definition.objects.filter(
            # We join simply with the concepts collected above which results in
            # a simpler query. This means that we won't collect definitions
            # without terms.
            #concept__in=concepts,
            concept__in=concept_qs,
            language=self.language_id,
        )
        for definition in definitions:
            concept = definition.concept_id
            if concept not in concepts:
                concepts[concept] = {}
            concepts[concept]["definition"] = definition

        return concepts

    def __str__(self):
        return _("#%(concept)s — language code: %(iso_code)s") % {'iso_code': self.language_id, 'concept': self.concept_id}

    def translations_html(self):
        translations = Translation.objects.filter(
                concept=self.concept,
                language=self.language,
        ).order_by("is_finalized")
        parts = []
        for translation in translations:
            if translation.is_finalized:
                parts.append(translation.translation_text)
            else:
                parts.append(format_html(_("{} <em>(not finalized)</em>"),
                                        translation.translation_text))
        return mark_safe(("<br>").join(parts))
    translations_html.short_description = _("Terms")

    def definition_html(self):
        try:
            definition = Definition.objects.filter(
                    concept=self.concept,
                    language=self.language,
            ).last()
        except Definition.DoesNotExist:
            return ""

        if definition.is_finalized:
            return definition.text
        else:
            return format_html(
                    _("{} <em>(not finalized)</em>"),
                    definition.text,
            )
            return _("%s (not finalized)") % definition.text
    definition_html.short_description = _("Definition")

    def date_html(self):
        if self.is_finalized:
            return self.date
        return ""
    date_html.short_description = _("Date")


@python_2_unicode_compatible
class Translation(models.Model, ConceptLangUrlMixin):
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, verbose_name=_("concept"))
    language = models.ForeignKey(Language, on_delete=models.PROTECT, verbose_name=_("language"))
    translation_text = models.CharField(max_length=100, verbose_name=_("translation text"))
    is_finalized = models.BooleanField(default=False, verbose_name=_("Is finalized"))
    administrative_status = models.ForeignKey(AdministrativeStatus, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("administrative status"))
    administrative_status_reason = models.ForeignKey(AdministrativeStatusReason, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("administrative status reason"))
    part_of_speech = models.ForeignKey(PartOfSpeech, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("part of speech"))
    grammatical_gender = models.ForeignKey(GrammaticalGender, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("grammatical gender"))
    grammatical_number = models.ForeignKey(GrammaticalNumber, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("grammatical number"))
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("translation")
        verbose_name_plural = _("translations")
        ordering = ['concept', 'language']

    def __str__(self):
        trans_data = {
            'term': self.translation_text,
            'iso_code': self.language_id,
            'concept': self.concept
        }
        return _("“%(term)s” (%(iso_code)s) for %(concept)s") % trans_data

    def save(self, *args, **kwargs):
        update_repr_cache = kwargs.pop("update_repr_cache", True)
        super(Translation, self).save(*args, **kwargs)
        if update_repr_cache:
            self.concept.update_repr_cache()

    def cmp_key(self):
        # used to sort terms according to their perceived worth
        keys = {
                "preferredTerm-admn-sts": 0,
                "": 1,
                None: 1,
                "admittedTerm-admn-sts": 2,
                "supersededTerm-admn-sts": 3,
                "deprecatedTerm-admn-sts": 4,
        }
        # We return a tuple with the "quality" key, and the text to allow
        # alphabetic sorting for all adminitted terms, for example.
        return (keys.get(self.administrative_status_id, 1), self.translation_text.lower())
        #TODO: for proper i18n, use locale aware sorting/lowercasing for the
        #language involved


@python_2_unicode_compatible
class Definition(models.Model, ConceptLangUrlMixin):
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, verbose_name=_("concept"))
    language = models.ForeignKey(Language, on_delete=models.PROTECT, verbose_name=_("language"))
    text = models.TextField(verbose_name=_("definition text"))
    is_finalized = models.BooleanField(default=False, verbose_name=_("is finalized"))
    source = models.URLField(blank=True, verbose_name=_("source"))
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("definition")
        verbose_name_plural = _("definitions")
        unique_together = ("concept", "language")

    def __str__(self):
        text = self.text
        concept = force_text(self.concept)
        if len(concept) > 40 and len(text) > 150:
            # This becomes quite long, and won't serve well in LogEntry. Let's
            # try to trim multiple terms in the concept:
            boundary = concept.find(",", 0, 35)
            if boundary < 0:
                # comma not found
                concept = concept[:35] + "…"
            else:
                concept = concept[:boundary]

        trans_data = {
            'iso_code': self.language_id,
            'concept': concept,
            'text': text
        }
        return _("Definition (%(iso_code)s) for %(concept)s: %(text)s") % trans_data


@python_2_unicode_compatible
class ExternalResource(models.Model):
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, verbose_name=_("concept"))
    language = models.ForeignKey(Language, null=True, blank=True, on_delete=models.PROTECT, verbose_name=_("language"))
    address = models.URLField(verbose_name=_("address"))
    link_type = models.ForeignKey(ExternalLinkType, on_delete=models.PROTECT, verbose_name=_("link type"))
    description = models.TextField(blank=True, verbose_name=_("description"))

    class Meta:
        verbose_name = _("external resource")
        verbose_name_plural = _("external resources")

    def __str__(self):
        if self.language_id:
            template = _("%(address)s (%(iso_code)s) for %(concept)s")
        else:
            template = _("%(address)s for %(concept)s")
        return template % {
            'address': self.address,
            'iso_code': self.language_id,
            'concept': self.concept,
        }


@python_2_unicode_compatible
class Proposal(models.Model):
    language = models.ForeignKey(Language, on_delete=models.PROTECT, verbose_name=_("language"))
    term = models.CharField(max_length=100, verbose_name=_("term"))
    definition = models.TextField(verbose_name=_("definition"))
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL, verbose_name=_("user"))
    sent_date = models.DateTimeField(auto_now_add=True, verbose_name=_("sent date"))
    for_glossary = models.ForeignKey(Glossary, on_delete=models.PROTECT, verbose_name=_("for glossary"))

    class Meta:
        verbose_name = _("proposal")
        verbose_name_plural = _("proposals")

    def __str__(self):
        return _("%(proposed_term)s (%(language)s)") % {'proposed_term': self.term, 'language': self.language}


@python_2_unicode_compatible
class ContextSentence(models.Model):
    translation = models.ForeignKey(Translation, on_delete=models.CASCADE, verbose_name=_("translation"))
    # NOTE: Changed the text field from TextField to Charfield limited to 250
    # chars due to MySQL constraints.
    text = models.CharField(max_length=250, verbose_name=_("text"))
    #source = models.URLField(blank=True, verbose_name=_("source"))#TODO

    class Meta:
        verbose_name = _("context sentence")
        verbose_name_plural = _("context sentences")
        unique_together = ("translation", "text")

    def __str__(self):
        trans_data = {
            'sentence': self.text,
            'translation': self.translation
        }
        return _("%(sentence)s for translation %(translation)s") % trans_data


@python_2_unicode_compatible
class CorpusExample(models.Model):
    translation = models.ForeignKey(Translation, on_delete=models.CASCADE, verbose_name=_("translation"))
    address = models.URLField(verbose_name=_("address"))
    description = models.TextField(blank=True, verbose_name=_("description"))

    class Meta:
        verbose_name = _("corpus example")
        verbose_name_plural = _("corpus examples")
        unique_together = ("translation", "address")

    def __str__(self):
        trans_data = {'address': self.address[:80], 'translation': self.translation}
        return _("%(address)s for translation %(translation)s") % trans_data


@python_2_unicode_compatible
class CollaborationRequest(models.Model):
    COLLABORATION_ROLE_CHOICES = (
        ('O', _('Glossary owner')),
        ('T', _('Terminologist')),
        ('S', _('Specialist')),
    )
    collaboration_role = models.CharField(max_length=2, choices=COLLABORATION_ROLE_CHOICES, verbose_name=_("collaboration role"))
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name=_("user"))
    sent_date = models.DateTimeField(auto_now_add=True, verbose_name=_("sent date"))
    for_glossary = models.ForeignKey(Glossary, on_delete=models.PROTECT, verbose_name=_("for glossary"))

    class Meta:
        verbose_name = _("collaboration request")
        verbose_name_plural = _("collaboration requests")
        unique_together = ("user", "for_glossary", "collaboration_role")

    def __str__(self):
        trans_data = {
            'user': self.user,
            'role': self.get_collaboration_role_display(),
            'glossary': self.for_glossary
        }
        return _("%(user)s requested %(role)s for %(glossary)s") % trans_data


@Field.register_lookup
class IntegerValue(Transform):
    lookup_name = 'integer'  # e.g. field__integer__in

    def as_sql(self, compiler, connection):
        sql, params = compiler.compile(self.lhs)
        sql = 'CAST(%s AS INT)' % sql
        return sql, params


def process_recent_changes(changes):
    """Helper to provide template variables for changes to certain models."""
    log = []
    changed_groups = sorted(changes, key=lambda o: o.content_type_id, reverse=True)
    changed_groups = itertools.groupby(changed_groups, key=lambda o: o.content_type_id)
    all_objects = {}

    for content_type_id, model_changes in changed_groups:
        Model = ContentType.objects.get_for_id(content_type_id).model_class()
        all_objects[content_type_id] = Model.objects.in_bulk(c.object_id for c in model_changes)

    # Some objects might have been deleted, so we have to check each one.
    for logentry in changes:
        models = all_objects[logentry.content_type_id]
        obj = models.get(int(logentry.object_id))
        if obj is None:
            # object since deleted. Let's try to get the concept.
            change = {"data": logentry}
            match = re.search(r'#([\d]+)', logentry.object_repr)
            concept_id = int(match.group(1))
            if match and Concept.objects.filter(pk=concept_id).exists():
                change["concept_id"] = concept_id
            log.append(change)
        else:
            # object is there - let's assume it is still the same one.
            log.append({
                "data": logentry,
                "concept_id": obj.concept_id,
            })
    return log
