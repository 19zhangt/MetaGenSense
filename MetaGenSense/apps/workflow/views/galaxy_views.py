# -*- coding: Utf-8 -*-
import os
import tempfile
import time
import urllib
import urlparse

import requests
from bioblend.galaxy.tools.inputs import inputs, dataset
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.shortcuts import render, render_to_response, redirect, HttpResponseRedirect
from django.template import RequestContext

from MetaGenSense.apps.lims.models import FileInformation, Project
from MetaGenSense.apps.lims.views.project_views import project_required
from ..forms import UploadForm
from ..libs.galaxyModule import MGSGalaxyInstance
from ..models import GalaxyUser, Workflow, RunWorkflow, WorkflowData


def connection_galaxy(func):
    """Initiating Galaxy connection"""

    def wrapper(request, project=None, *args, **kwargs):

        gu, created = GalaxyUser.objects.get_or_create(user=request.user)

        if not gu.api_key:
            return redirect('galaxy_account')

        gi = MGSGalaxyInstance(url=settings.GALAXY_SERVER_URL, key=gu.api_key)

        try:
            gu_info = gi.users.get_current_user()

        except:
            return redirect('galaxy_account')  # "Provided API key is not valid.

        # personnal folder
        gi.roles = gu_info.get("email")

        user_input_path = os.path.join(settings.GALAXY_IMPORT_DIR, gi.roles)

        gi.library_name = gi.roles  # TODO add field in galaxyuser model
        gi.galaxy_input_path = user_input_path
        gi.MGS_folder = settings.MGS_GALAXY_FOLDER

        return func(request, project, gi, *args, **kwargs)

    return wrapper


@login_required
@project_required
@connection_galaxy
def galaxydir_to_dataset(request, project=None, gi=None):
    """import les fichiers situes dans le repertoires links dans galaxy
    """
    msg = "Not ajax"
    if request.is_ajax():
        if gi.library_id:
            dataset = gi.get_or_create_dataset(project, gi.library_id)
            for data in dataset:
                # recupere l'id du folder du projet
                if (data['type'] == 'folder') and (project == data['name'].split('/')[-1]):

                    try:
                        importedfiles = gi.import_file_to_galaxy(gi.library_id, data['id'], project)
                    except Exception, e:
                        print e
                        messages.add_message(request, messages.WARNING,
                                             "Please put file(s) into your galaxy links directory at: \n%s" % (
                                                 os.path.join(gi.galaxy_input_path, gi.MGS_folder, project)))

                        return render_to_response("galaxy/includes/dataset.html",
                                                  context_instance=RequestContext(request))

                    dataset = gi.display_folders(gi.library_id, project)

                    # format names
                    for data in dataset:
                        if data['type'] == 'file':
                            tmp = data['name'].rsplit('/', 1)
                            data['name'] = tmp[-1]

                    return render_to_response("galaxy/includes/dataset.html",
                                              {'dataset': dataset, 'importedfiles': importedfiles})
            else:
                msg = "dataset is empty or not does not contenain %s folder" % (project)
        else:
            msg = "You need to configure Galaxy Library"

    messages.add_message(request, messages.WARNING, msg)
    return render_to_response("galaxy/includes/dataset.html", context_instance=RequestContext(request))


@login_required
@project_required
@connection_galaxy
def remove_library_dataset(request, dataset_id, project=None, gi=None):
    """
        delete "overimported" dataset
    """
    gi.libraries.delete_library_dataset(gi.library_id, dataset_id, purged=False)

    return redirect('workflow_datasets')


@login_required
@project_required
@connection_galaxy
def workflow_datasets(request, project=None, gi=None):
    """Display global view display
     - list of histories
     - list of dataset to import data in history
     - upload file forms
     :param project : current project
     :param gi : galaxy instance"""

    dataset = ''
    histories = ''

    histories = gi.histories.get_histories()

    # import les donnees dans l'historique de l'utilisateur
    if request.method == "POST":
        selected_files = request.POST.getlist('file')
        suffix = request.POST.get('newhistoryname', "")
        if selected_files:
            history_id = gi.import_dataset_to_history(project, gi.library_id, selected_files, suffix)
            return redirect('galaxy_history_detail', history_id)

        else:
            return render(request, 'galaxy/datasets.html', {'histories': histories,
                                                            'message': "Please select file(s)"})

    # TODO supprimer les historiques qui ne concernent pas le projet

    return render(request, 'galaxy/datasets.html', {'histories': histories,
                                                    'message': "",
                                                    'uploadform': UploadForm()})


@login_required
@project_required
@connection_galaxy
def get_galaxy_dataset(request, project, gi):
    """Ajax fct call by workflow_datasets page"""
    dataset = ""
    if request.is_ajax():
        if gi.library_id:
            dataset = gi.get_or_create_dataset(project, gi.library_id)

            # format names 
            for data in dataset:
                if data['type'] == 'file':
                    tmp = data['name'].rsplit('/', 1)
                    data['name'] = tmp[-1]
        else:
            messages.add_message(request, messages.WARNING, "You need to configure Galaxy Library")

    return render(request, 'galaxy/includes/dataset.html', {'dataset': dataset})


@login_required
@project_required
@connection_galaxy
def galaxy_history_detail(request, project, gi, history_id):
    """display detail of one history and galaxy workflows launched
    """

    hist_info = ''
    history_content = ''
    wkfs = Workflow.objects.all()

    for wk_obj in wkfs:
        wf = gi.workflows.show_workflow(wk_obj.wf_key)
        err = wf.get("err_msg")
        if err:
            return render(request, 'galaxy/datasets.html', {'histories': gi.histories.get_histories(),
                                                            'message': "Please select file(s)"})
        else:
            i_inputs = wf['inputs'].keys()
            wk_obj.nb_input = len(i_inputs)

    if gi:
        hist_info = gi.histories.show_history(history_id, contents=False, deleted=False)
        history_content = gi.histories.show_history(history_id, contents=True, deleted=False)

        print hist_info
        # trop lent: 
        # details_file = []
        # for i in history_content:  
        #    details_file.append(gi.datasets.show_dataset(i['id']))

        # ajout la description status dans les details des fichiers 
        for key, values in hist_info['state_ids'].iteritems():
            for history_file in history_content:
                if history_file["id"] in values:
                    history_file["status"] = key

    return render(request, 'galaxy/launch_workflow.html', {
        'history_info': hist_info,  # get summary
        'history_content': history_content,
        'workflows': wkfs  # get file into history
    })


@login_required
@project_required
@connection_galaxy
def galaxy_history_list(request, project, gi):
    """
    """
    histories = gi.histories.get_histories()

    return render_to_response("galaxy/includes/dataset.html", {'dataset': histories})


@login_required
@project_required
@connection_galaxy
def download_file(request, project, gi, file_id):
    """permet a l'utilisateur de telecharger le fichier grace a l'api"""

    data = gi.datasets.show_dataset(dataset_id=file_id)

    params = urllib.urlencode({'to_ext': data["data_type"], 'key': gi.key}, True)
    url = urlparse.urljoin(gi.base_url, data['download_url'])
    response = '%s/?%s' % (url, params)

    # TODO test if bigDATA
    return HttpResponseRedirect(response)


@login_required
@project_required
@connection_galaxy
def save_file_information(request, project, gi, file_id):
    """import file in the synbiowatch and save metadata in the database
    """
    data = gi.datasets.show_dataset(dataset_id=file_id)
    name_history = gi.histories.show_history(data['history_id'])['name']
    project_obj = Project.objects.get(name=project)

    try:
        runWf = RunWorkflow.objects.get(name=name_history)
    except:
        messages.warning(request, "Workflow data is not linked with run workflow some information are missing.\n" +
                         "Please relaunch workflow in a new history with Synbiowatch interface")
        return redirect("galaxy_workflow")

    # TODO test if bigDATA 
    # recupere l'url de telechargement
    url = urlparse.urljoin(gi.base_url, data['download_url'])
    params = urllib.urlencode({'to_ext': "html", 'key': gi.key}, True)
    # response = urllib2.urlopen('%s?%s' % (url, params))
    r = requests.get('%s?%s' % (url, params))

    file_info = FileInformation(name=data['name'],
                                format=data['data_type'],
                                type="",
                                size=data['file_size'],
                                author="",
                                # creation_date="",
                                # file_path="",
                                project=project_obj
                                )
    file_info._path = '%s/%s/%s' % (settings.ANALYSE_FOLDER, project, name_history)
    file_info.file_path.save(data['name'],
                             ContentFile(r.content),
                             save=False)
    file_info.save()
    print file_info
    worflowdata = WorkflowData(data=file_info,
                               input=0,
                               output=1,  # TODO Count
                               id_run_wf=runWf
                               )
    worflowdata.save()
    messages.success(request, file_id)
    return redirect('galaxy_history_detail', data['history_id'])


@login_required
@project_required
@connection_galaxy
def export_output(request, project, gi, file_id, tool_id="export_sbw"):
    """Export data in galaxy MetaGenSense output directory"""
    """add the name of project on file name"""

    data = gi.datasets.show_dataset(dataset_id=file_id)
    hist_id = data['history_id']

    myinputs = inputs().set("prefix", project).set("input", dataset(file_id))

    tool_outputs = gi.tools.run_tool(history_id=hist_id, tool_id=tool_id, tool_inputs=myinputs)

    if tool_outputs:
        messages.warning(request, "Export is in progress, your file will be available: " + project + '_' + data['name'])
    return redirect('galaxy_history_detail', history_id=hist_id)


@login_required
@project_required
@connection_galaxy
def upload_file_to_history(request, project, gi):
    """
        Upload file into Galaxy Server
    """
    if request.method == 'POST':
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            myfile = form.cleaned_data['file_field']
            tmpfile = tempfile.NamedTemporaryFile()
            for chunk in myfile.chunks():
                tmpfile.write(chunk)
            tmpfile.flush()
            # naive methode datetime
            history_id = gi.histories.create_history(name=project + '_' + time.strftime("%d-%m-%Y %H:%M:%S")).get("id")
            hist = gi.tools.upload_file(tmpfile.name, history_id, file_name=myfile.name)
            tmpfile.close()

        return redirect('galaxy_history_detail', history_id)
    else:
        return redirect('galaxy_workflow')
