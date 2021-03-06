# -*- coding: UTF-8 -*-
#
# Copyright 2011, 2013 Leandro Regueiro
# Copyright 2017-2018 Friedel Wolff
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

from xml.dom import minidom

from django.contrib.admin.models import LogEntry, ADDITION
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render
from django.utils.encoding import force_text
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.csrf import csrf_protect

from terminator.forms import ImportForm, SearchForm
from terminator.models import *


def getText(nodelist):
    """
    Extract the stripped text from all text nodes in a node list.
    This is used for getting the text from text nodes in TBX files.
    """
    rc = u""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc += node.data
    return rc.strip()


def lookup_dict(model, values=True):
    qs = model.objects.all()
    if values:
        return dict((x.tbx_representation.lower(), x.pk) for x in qs)
    return dict((x.tbx_representation.lower(), x) for x in qs)


def import_uploaded_file(uploaded_file, imported_glossary):
    #TODO Split this function in several shorter functions.
    #TODO Validate the uploaded file in order to check that it is a valid TBX
    # file, or even a text file.
    #TODO Use lxml/etree instead of xml.dom.minidom.
    tbx_file = minidom.parse(uploaded_file)

    #TODO Perhaps add the title and description from the TBX file to the
    # glossary instead of using the ones provided in the import form. Or maybe
    # just append the TBX values (if provided) to the description (only the
    # description) provided in the import form.

    #glossary_name = getText(tbx_file.getElementsByTagName(u"title")[0].childNodes)
    #glossary_description = getText(tbx_file.getElementsByTagName(u"p")[0].childNodes)
    #imported_glossary.name = glossary_name
    #imported_glossary.description = glossary_description
    #imported_glossary.save()

    # Keep all of these in memory for repeated use.
    languages = set(Language.objects.all().values_list('iso_code', flat=True))
    parts_of_speech = lookup_dict(PartOfSpeech)
    admin_statusses = lookup_dict(AdministrativeStatus, values=False)
    genders = lookup_dict(GrammaticalGender)
    numbers = lookup_dict(GrammaticalNumber)
    link_types = lookup_dict(ExternalLinkType)

    concept_object = None
    concept_list = []
    concept_pool = {}
    language_pool = set()
    for concept_tag in tbx_file.getElementsByTagName(u"termEntry"):
        concept_id = concept_tag.getAttribute(u"id")
        # The concept id should be unique on all the TBX file.
        if concept_id in concept_pool:
            excp_msg = (_("There is already another \"%s\" tag with an "
                          "\"%s\" attribute with the value \"%s\" in the "
                          "TBX file.") %
                        ("termEntry", "id", concept_id))
            excp_msg += force_text(_("\n\nIf you want to import this TBX file"
                                  " you must fix this in the TBX file."))
            raise Exception(excp_msg)
        concept_object = Concept(glossary=imported_glossary)
        concept_object.save()
        concept_pool_entry = {"object": concept_object}

        # Get the subject field and broader concept for the current
        # termEntry tag.
        # NOTE: Be careful because the following returns all the descrip
        # tags, even from langSet or lower levels.
        for descrip_tag in concept_tag.getElementsByTagName(u"descrip"):
            if descrip_tag.getAttribute("type") == "subjectField":
                # Only accept subjectFields that are inside a descripGrp
                # and that have a sibling ref tag pointing to a concept.
                # NOTE: This means that the subjectFields are other
                # concepts in the glossary, and thus the value stored in
                # the <descrip type="subjectField"> tag is not used at all.
                #TODO Consider if it would be worth raising an exception
                # with an explanatory message in the case that it is not
                # inside a descripGrp tag.
                if descrip_tag.parentNode.tagName == "descripGrp":
                    ref_tags = descrip_tag.parentNode.getElementsByTagName(u"ref")
                    if ref_tags:
                        # Only the first ref tag in the descripGrp is used.
                        concept_pool_entry["subject"] = ref_tags[0].getAttribute(u"target")
            if descrip_tag.getAttribute(u"type") == u"broaderConceptGeneric":
                broader = descrip_tag.getAttribute(u"target")
                if broader:
                    concept_pool_entry["broader"] = broader

        # Get the related concepts information for the current termEntry.
        concept_pool_entry["related"] = []
        for ref_tag in concept_tag.getElementsByTagName(u"ref"):
            if ref_tag.getAttribute(u"type") == u"crossReference":
                # The crossReference should be just below the termEntry tag.
                if ref_tag.parentNode == concept_tag:
                    related_key = ref_tag.getAttribute(u"target")
                    if related_key:
                        concept_pool_entry["related"].append(related_key)
        # If the termEntry has no related concepts remove the key related
        # from concept_pool_entry.
        if not concept_pool_entry["related"]:
            concept_pool_entry.pop("related")

        concept_list.append(concept_object)
        # Save all the concept relations for setting them when the TBX file
        # is fully readed.
        if concept_id:
            concept_pool[concept_id] = concept_pool_entry

        src_translations = []
        for language_tag in concept_tag.getElementsByTagName(u"langSet"):
            lang_id = language_tag.getAttribute(u"xml:lang")
            if not lang_id:
                excp_msg = (_("\"%s\" tag without \"%s\" attribute in "
                              "concept \"%s\".") %
                            ("langSet", "xml:lang", concept_id))
                excp_msg += force_text(_("\n\nIf you want to import this TBX "
                                      "file you must add that attribute "
                                      "to that tag in the TBX file."))
                raise Exception(excp_msg)
            if lang_id not in languages:
                excp_msg = (_("\"%s\" tag with code \"%s\" in its \"%s\" "
                              "attribute, found in concept \"%s\", but "
                              "there is no Language with that code in "
                              "Terminator.") %
                            ("langSet", lang_id, "xml:lang", concept_id))
                excp_msg += force_text(_("\n\nIf you want to import this TBX "
                                      "file, either add this language to "
                                      "Terminator, or change the \"%s\" "
                                      "attribute for this \"%s\" tag in "
                                      "the TBX file.") %
                                    ("xml:lang", "langSet"))
                raise Exception(excp_msg)

            language_pool.add(lang_id)
            # Get the definition for each language.
            # NOTE: Be careful because the following returns all the
            # descrip tags, and not all of them are definitions.
            for descrip_tag in language_tag.getElementsByTagName(u"descrip"):
                descrip_type = descrip_tag.getAttribute(u"type")
                if descrip_type == u"definition":
                    definition_text = getText(descrip_tag.childNodes)
                    if definition_text:
                        definition_object = Definition(
                                concept=concept_object,
                                language_id=lang_id,
                                text=definition_text,
                                is_finalized=False,
                        )
                        definition_object._history_user = None
                        # If the definition is inside a descripGrp tag, it
                        # may have a source.
                        if descrip_tag.parentNode.tagName == "descripGrp":
                            definition_source_list = descrip_tag.parentNode.getElementsByTagName(u"xref")
                            if definition_source_list:
                                #TODO There is no check to see if this xref
                                # xref tag has type="xSource".
                                definition_object.source = definition_source_list[0].getAttribute(u"target")
                        definition_object.save()
                    # Each langSet should have at most one definition, and
                    # since Terminator doesn't import other descrip tags at
                    # langSet level then stop looping.
                    break

            # Get the external resources for each language.
            for xref_tag in language_tag.getElementsByTagName(u"xref"):
                # If the xref tag is a child of the langSet tag, or in
                # other words, if the xref tag is not inside a descripGrp
                # tag alongside a definition in order to provide the source
                # for that definition.
                if xref_tag.parentNode == language_tag:
                    resource_type = xref_tag.getAttribute(u"type").lower()
                    try:
                        resource_link_type = link_types[resource_type]
                    except KeyError:
                        excp_msg = (_("External Link Type \"%s\", found "
                                      "inside a \"%s\" tag in the \"%s\" "
                                      "language in concept \"%s\", doesn't"
                                      " exist in Terminator.") %
                                    (resource_type, "xref", lang_id,
                                     concept_id))
                        excp_msg += force_text(_("\n\nIf you want to import "
                                              "this TBX file, either add "
                                              "this External Link Type to "
                                              "Terminator, or change this "
                                              "External Link Type on the "
                                              "TBX file."))
                        raise Exception(excp_msg)
                    resource_target = xref_tag.getAttribute(u"target")
                    resource_description = getText(xref_tag.childNodes)
                    # TODO If resource_description doesn't exist raise an
                    # exception.
                    if resource_target and resource_description:
                        external_resource_object = ExternalResource(
                                concept=concept_object,
                                language_id=lang_id,
                                address=resource_target,
                                link_type_id=resource_link_type,
                                description=resource_description,
                        )
                        external_resource_object.save()

            # Get the translations and related data for each language.
            tig_tags = language_tag.getElementsByTagName(u"tig")
            #TODO Make the import work for ntig tags too.

            for translation_tag in tig_tags:
                term_tags = translation_tag.getElementsByTagName(u"term")
                # Proceed only if there is at least one term tag inside
                # this tig or ntig tag.
                if not term_tags:
                    continue

                # The next line only works with the first term tag
                # skipping other term tags if present.
                translation_text = getText(term_tags[0].childNodes)
                if translation_text:
                    translation_object = Translation(
                            concept=concept_object,
                            language_id=lang_id,
                            translation_text=translation_text,
                    )
                    if lang_id == imported_glossary.source_language_id:
                        src_translations.append(translation_object)

                for termnote_tag in translation_tag.getElementsByTagName(u"termNote"):
                    termnote_type = termnote_tag.getAttribute(u"type")
                    #TODO the Parts of Speech, Grammatical Genders,
                    # Grammatical Numbers, Administrative Statuses and
                    # Administrative Status Reasons specified in the
                    # TBX file may not exist in the Terminator
                    # database, so the import process will fail. Maybe
                    # it should create those missing entities, but it
                    # may fill the database with duplicates.
                    #TODO the Parts of Speech, Grammatical Genders,
                    # Grammatical Numbers, Administrative Statuses and
                    # Administrative Status Reasons can only be used
                    # for certain languages, and the actual importing
                    # code doesn't respect these constraints.
                    if termnote_type == u"partOfSpeech":
                        #TODO Since in some TBX files the Part of
                        # Speech is capitalized it should be converted
                        # to lowercase in the next line in order to get
                        # the Part of Speech import working.
                        pos_text = getText(termnote_tag.childNodes)
                        try:
                            pos_id = parts_of_speech[pos_text.lower()]
                        except KeyError:
                            raise Exception(_("Part of Speech \"%s\", "
                                              "found in \"%s\" "
                                              "translation for \"%s\" "
                                              "language in concept "
                                              "\"%s\", doesn't exist "
                                              "in Terminator.\n\nIf "
                                              "you want to import this"
                                              " TBX file, either add "
                                              "this Part of Speech to "
                                              "Terminator, or change "
                                              "this Part of Speech on "
                                              "the TBX file.") %
                                            (pos_text,
                                             translation_text,
                                             lang_id, concept_id))

                        translation_object.part_of_speech_id = pos_id
                    elif termnote_type == u"grammaticalGender":
                        gramm_gender_text = getText(termnote_tag.childNodes)
                        try:
                            gender_id = genders[gramm_gender_text.lower()]
                        except KeyError:
                            raise Exception(_("Grammatical Gender "
                                              "\"%s\", found in \"%s\""
                                              " translation for \"%s\""
                                              " language in concept "
                                              "\"%s\", doesn't exist "
                                              "in Terminator.\n\nIf "
                                              "you want to import this"
                                              " TBX file, either add "
                                              "this Grammatical Gender"
                                              " to Terminator, or "
                                              "change this Grammatical"
                                              " Gender on the TBX "
                                              "file.") %
                                            (gramm_gender_text,
                                             translation_text,
                                             lang_id, concept_id))
                        translation_object.grammatical_gender_id = gender_id
                    elif termnote_type == u"grammaticalNumber":
                        gramm_number_text = getText(termnote_tag.childNodes)
                        try:
                            number_id = numbers[gramm_number_text.lower()]
                        except KeyError:
                            raise Exception(_("Grammatical Number "
                                              "\"%s\", found in \"%s\""
                                              " translation for \"%s\""
                                              " language in concept "
                                              "\"%s\", doesn't exist "
                                              "in Terminator.\n\nIf "
                                              "you want to import this"
                                              " TBX file, either add "
                                              "this Grammatical Number"
                                              " to Terminator, or "
                                              "change this Grammatical"
                                              " Number on the TBX "
                                              "file.") %
                                            (gramm_number_text,
                                             translation_text,
                                             lang_id, concept_id))
                        translation_object.grammatical_number_id = number_id
                    elif termnote_type == u"processStatus":
                        # Values of processStatus different from
                        # finalized are ignored.
                        if getText(termnote_tag.childNodes) == u"finalized":
                            translation_object.is_finalized = True
                    elif termnote_type == u"administrativeStatus":
                        admin_status_text = getText(termnote_tag.childNodes)
                        try:
                            admin_status = admin_statusses[admin_status_text.lower()]
                        except KeyError:
                            raise Exception(_("Administrative Status "
                                              "\"%s\", found in \"%s\""
                                              " translation for \"%s\""
                                              " language in concept "
                                              "\"%s\", doesn't exist "
                                              "in Terminator.\n\nIf "
                                              "you want to import this"
                                              " TBX file, either add "
                                              "this Administrative "
                                              "Status to Terminator, "
                                              "or change this "
                                              "Administrative Status "
                                              "on the TBX file.") %
                                            (admin_status_text,
                                             translation_text,
                                             lang_id, concept_id))
                        translation_object.administrative_status = admin_status
                        # If the Administrative Status is inside a
                        # termGrp tag it may have an Administrative
                        # Status Reason.
                        if admin_status.allows_reason and termnote_tag.parentNode != translation_tag:
                            reason_tag_list = termnote_tag.parentNode.getElementsByTagName(u"note")
                            if reason_tag_list:
                                try:
                                    reason_object = AdministrativeStatusReason.objects.get(name__iexact=getText(reason_tag_list[0].childNodes))
                                except AdministrativeStatusReason.DoesNotExist:
                                    pass #TODO Raise an exception
                                else:
                                    translation_object.administrative_status_reason = reason_object
                    elif termnote_type == u"termType":
                        # It might be phraseologicalUnit, acronym or
                        # abbreviation that in Terminator are internally
                        # represented as PartOfSpeech objects.
                        termtype_text = getText(termnote_tag.childNodes)
                        try:
                            pos_id = parts_of_speech[pos_text.lower()]
                        except KeyError:
                            raise Exception(_("TermType \"%s\", found "
                                              "in \"%s\" translation "
                                              "for \"%s\" language in "
                                              "concept \"%s\", doesn't"
                                              " exist in Terminator.\n"
                                              "\nIf you want to import"
                                              " this TBX file, either "
                                              "add this TermType as "
                                              "another Part of Speech "
                                              "to Terminator, or "
                                              "change this TermType on"
                                              " the TBX file.\n\nNote:"
                                              " Terminator stores this"
                                              " TermType values as "
                                              "Part of Speech.") %
                                            (termtype_text,
                                             translation_text,
                                             lang_id, concept_id))
                        translation_object.part_of_speech_id = pos_id

                for note_tag in translation_tag.getElementsByTagName(u"note"):
                    # Ensure that this note tag is not at lower levels
                    # inside the translation tag.
                    if note_tag.parentNode == translation_tag:
                        note_text = getText(note_tag.childNodes)
                        if note_text:
                            translation_object.note = note_text
                        # Each translation should have at most one
                        # translation note, so stop looping.
                        break

                # Remove the gender and number for the translation if
                # it doesn't have a Part of Speech.
                if (translation_object.grammatical_gender_id or translation_object.grammatical_number_id) and not translation_object.part_of_speech_id:
                    translation_object.grammatical_gender = None
                    translation_object.grammatical_number = None

                # Save the translation because the next tags can create
                # objects that will refer to the translation object and
                # thus it should have an id set.
                translation_object.save(update_repr_cache=False)

                # Get the context phrase for the current translation.
                for descrip_tag in translation_tag.getElementsByTagName(u"descrip"):
                    descrip_type = descrip_tag.getAttribute(u"type")
                    if descrip_type == u"context":
                        phrase_object = ContextSentence(
                                translation=translation_object,
                                text=getText(descrip_tag.childNodes),
                        )
                        phrase_object.save()

                # Get the corpus examples for the current translation.
                for xref_tag in translation_tag.getElementsByTagName(u"xref"):
                    xref_type = xref_tag.getAttribute(u"type")
                    if xref_type == u"corpusTrace":
                        xref_target = xref_tag.getAttribute(u"target")
                        xref_description = getText(xref_tag.childNodes)
                        if xref_target and xref_description:
                            corpus_example_object = CorpusExample(
                                    translation=translation_object,
                                    address=xref_target,
                                    description=xref_description,
                            )
                            corpus_example_object.save()

            if src_translations:
                concept_object.repr_cache = concept_object.repr_from(src_translations)

    #populate glossary.other_languages
    source_lang = imported_glossary.source_language_id
    if source_lang in language_pool:
        language_pool.remove(source_lang)
    imported_glossary.other_languages.add(*Language.objects.filter(iso_code__in=language_pool))

    # Once the file has been completely parsed is time to add the concept
    # relationships and save the concepts. This is done this way since some
    # termEntry refer to termEntries that haven't been parsed yet.
    try:
        for concept_key, current in concept_pool.items():
            if "subject" in current:
                try:
                    current["object"].subject_field = concept_pool[current["subject"]]["object"]
                except KeyError:
                    excp_msg = (_("The concept \"%s\" uses the concept"
                                  " \"%s\" as its subject field, but that "
                                  "concept id doesn't exist in the TBX "
                                  "file.") %
                                (concept_key, current["subject"]))
                    excp_msg += force_text(_("\n\nIf you want to import this "
                                          "TBX file you must fix this."))
                    raise Exception(excp_msg)
            if "broader" in current:
                try:
                    current["object"].broader_concept = concept_pool[current["broader"]]["object"]
                except KeyError:
                    excp_msg = (_("The concept \"%s\" uses the concept"
                                  " \"%s\" as its broader concept, but "
                                  "that concept id doesn't exist in the "
                                  "TBX file.") %
                                (concept_key, current["broader"]))
                    excp_msg += force_text(_("\n\nIf you want to import this "
                                          "TBX file you must fix this."))
                    raise Exception(excp_msg)
            if "related" in current:
                for related_key in current["related"]:
                    try:
                        current["object"].related_concepts.add(concept_pool[related_key]["object"])
                    except KeyError:
                        excp_msg = (_("The concept \"%s\" uses the concept"
                                      " \"%s\" as one of its related "
                                      "concepts (cross reference), but "
                                      "that concept id doesn't exist in "
                                      "the TBX file.") %
                                    (concept_key, related_key))
                        excp_msg += force_text(_("\n\nIf you want to import "
                                              "this TBX file you must fix "
                                              "this."))
                        raise Exception(excp_msg)
            # Save the concept object once its relationships with other
            # concepts in the glossary are set.
            # TODO Save the concept object only if it is changed.
            current["object"].save()
    except:
        # In case of failure during the concept relationships assignment
        # the subject_field and broader_concept must be set to None in
        # order to delete all the glossary data because this two fields
        # have on_delete=models.PROTECT
        for concept_dict in concept_pool.values():
            concept = concept_dict["object"]
            concept.subject_field = None
            concept.broader_concept = None
            # The next line is unnecessary, but keep it because in the
            # future it might be necessary.
            #concept.related_concepts.clear()
            concept.save()
        # Raise the exception again in order to show the error in the UI.
        raise

    if len(concept_pool) == 0 and concept_object:
        # Nothing was added to the pool (no IDs?), but there was at least one
        # concept. We still have to save for the sake of the repr_cache.
        for concept in concept_list:
            concept.save()


# TODO: need much better permissions checking:
@login_required
@csrf_protect
def import_view(request):
    context = {
        'search_form': SearchForm(),
        'next': request.get_full_path(),
    }
    if request.method == 'POST':
        import_form = ImportForm(request.POST, request.FILES)
        if import_form.is_valid():
            glossary = import_form.save()
            try:
                with transaction.atomic():
                    import_uploaded_file(request.FILES['imported_file'], glossary)
            except Exception as e:
                glossary.delete()
                import_error_message = _("The import process failed:\n\n")
                import_error_message += force_text(e.args[0])
                context['import_error_message'] = import_error_message
            else:
                import_message = _("TBX file succesfully imported.")
                context['import_message'] = import_message
                context['glossary'] = glossary
                import_form = ImportForm()
                LogEntry.objects.log_action(
                    user_id=request.user.pk,
                    content_type_id=ContentType.objects.get_for_model(glossary).pk,
                    object_id=glossary.pk,
                    object_repr=force_text(glossary),
                    action_flag=ADDITION,
                )
    else:
        import_form = ImportForm()
    context['import_form'] = import_form
    return render(request, 'import.html', context)
