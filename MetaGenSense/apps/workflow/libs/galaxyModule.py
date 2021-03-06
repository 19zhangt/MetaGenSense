# -*-coding:Utf-8 -*

import os
import time

from bioblend.galaxy import GalaxyInstance


class MGSGalaxyInstance(GalaxyInstance):
    """to custom bioblend request for MGS"""
    
    def __init__(self, url, key):                
        GalaxyInstance.__init__(self, url, key)   
        
        self.galaxy_input_path = ''
        self.library_name = 'MGS' #library to store data folder
        self.MGS_folder = ''      #name folder to store library of MetaGenSense in galaxy  
        self.roles = ''
        self.library_id = self.get_library_id()

    def get_library_id(self):

        libraries = self.libraries.get_libraries(name=self.library_name)
        # recupere l'id de la 1ere library de l'utilisateur
        if not libraries:
            libraries = self.libraries.get_libraries()
        try:
            return libraries[0].get("id")
        except Exception:
            return None


    def display_folders(self, library_id, project):
        "Retourne le contenu du dossier du projet situé dans le reperoire MetaGenSense de Galaxy "
        
        folders = self.libraries.show_library(library_id=library_id, contents=True)
        project_folder = []
        
        for data in folders:
            if (self.MGS_folder + '/' + project) in data['name']:
                project_folder.append(data)
                
        return project_folder

    def display_histoiries(self, project):
        
        folders = self.histories.get_histories()
        project_folder = []
        
        for f in folders:
            if (self.MGS_folder + '/' + project) in f['name']:
                project_folder.append(f)
                
        return project_folder
        
    def get_folder_by_path(self, folders, folder_path):
        # take a list of folder return galaxy folder id or '' if not found
        for f in folders:
            if f['name'] == folder_path:
                return f
    
    def mgs_create_folder(self, library_id, folder_path, folders=None):
        """
            Crée les dossiers dans le reperoire MetaGenSense de Galaxy 
            a l'aide d'un path et de l'id galaxy de la librairie à utiliser.
        """
        
        # TODO a optimiser
        # on recupere tout les fichiers de l'utilisateur de galaxy
        if not folders:
            folders = self.libraries.show_library(library_id=library_id, contents=True)
              
        # on recupere l'id du repertoire parent
        parent_folder_path, folder_name = folder_path.rsplit(os.sep, 1)

        if not parent_folder_path:
            root_path = os.sep
            parent_folder = self.get_folder_by_path(folders, root_path)
            
        else:
            parent_folder = self.get_folder_by_path(folders, parent_folder_path)
            print parent_folder 
        
        # si le parent n'exite pas et si le parent n'est pas la racine
        if not parent_folder:
            parent_folder = self.mgs_create_folder(library_id, parent_folder_path, folders)  

        newfolder = self.libraries.create_folder(library_id=library_id,
                                                 folder_name=folder_name,
                                                 base_folder_id=parent_folder['id'],
                                                 )
        return newfolder[0]
                
    def get_or_create_dataset(self, project, library_id):
        """
        Retourne le contenu du dossier du projet situe dans le reperoire MetaGenSense de Galaxy
        crée le repertoire dans galaxy s'il n'exite pas 
        """
        project_folders = self.display_folders(library_id, project)
        
        if not project_folders:

            path = os.path.join(self.MGS_folder, project)
            self.mgs_create_folder(library_id, path)
            
            # mise a jour
            project_folders = self.display_folders(library_id, project)
            
        return project_folders
        
    def import_file_to_galaxy(self, library_id, folder_id, project):
        """ Import file into galaxy in the library folder from link/'user'/"MetaGenSense"/project name
            Return list of imported files
        """
        server_dir = os.path.join(self.galaxy_input_path, self.MGS_folder.strip(os.sep), project)
        
        print server_dir, self.galaxy_input_path, self.MGS_folder, project
        return self.libraries.upload_file_from_server(library_id, server_dir, folder_id=folder_id)

    def import_dataset_to_history(self, project, library_id, dataset_id, suffix=""):
        
        # TODO rajouter des filtres + timezone
        # test si l'historique deja cree
        if suffix:
            suffix = '_' + suffix
            
        history_list = self.histories.get_histories(name=project + '_' + time.strftime("%d-%m-%Y") + suffix)
        
        if history_list:
            ghistory = history_list[0]
        else: 
            ghistory = self.histories.create_history(project + '_' + time.strftime("%d-%m-%Y") + suffix)
            
        history_id = ghistory['id']    

        print 'history:', ghistory    
        
        # self.histories.create_history_tag(history_id, 'MGS')
        # self.histories.update_history(history_id, annotation="MGS")
        
        for selectedfile in dataset_id:
            payload = {'from_ld_id': selectedfile, 'content': selectedfile, 'source': 'library', 'roles': self.roles}   
            print payload
        
            # self.histories.upload_dataset_from_library(library_id, lib_dataset_id ) "not implemented with roles attribut"
            self.histories._post(payload, id=history_id, contents=True)
            
        return history_id
            
