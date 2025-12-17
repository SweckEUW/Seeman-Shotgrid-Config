# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import hou
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()

# WICHTIG: Klasse umbenannt, damit sie sich nicht mit dem Standard beißt!
class SeacarusLayerCollector(HookBaseClass):
    """
    Collector that operates on the current houdini session. Should inherit from
    the basic collector hook.
    """

    @property
    def settings(self):
        """
        Dictionary defining the settings that this collector expects to receive.
        """

        # grab any base class settings
        # WICHTIG: Hier den neuen Klassennamen nutzen
        collector_settings = super(SeacarusLayerCollector, self).settings or {}

        # settings specific to this collector
        houdini_session_settings = {
            "Work Template": {
                "type": "template",
                "default": None,
                "description": "Template path for artist work files.",
            },
        }

        # update the base settings with these settings
        collector_settings.update(houdini_session_settings)

        return collector_settings

    def process_current_session(self, settings, parent_item):
        """
        Analyzes the current Houdini session and parents a subtree of items
        under the parent_item passed in.
        """
        
        # 1. Standard: Hip File einsammeln
        # create an item representing the current houdini session
        session_item = self.collect_current_houdini_session(settings, parent_item)

        print("Houdini Session Item collected: %s" % session_item.name)

        # 3. CUSTOM: Seacarus Layer Exporter einsammeln
        # Wir hängen diese Items auch unter das Session Item
        self.collect_seacarus_layers(session_item)


    def collect_seacarus_layers(self, parent_item):
        """
        Sucht spezifisch nach 'seacarus_layer_exporter' Nodes.
        Diese werden gesammelt, auch wenn noch keine Output-Datei existiert (da wir sie rendern wollen).
        """
        hda_name = "seacarus_layer_exporter"
        categories = [hou.lopNodeTypeCategory(), hou.objNodeTypeCategory()]
        
        found_nodes = []
        for cat in categories:
            node_type = hou.nodeType(cat, hda_name)
            if node_type:
                print(f"Gefundenen Node-Typ: {node_type.name()}")
                found_nodes.extend(node_type.instances())

        if not found_nodes:
            self.logger.info(f"Keine '{hda_name}' Nodes gefunden.")
            return

        self.logger.info(f"Verarbeite {len(found_nodes)} Seacarus Layer Nodes...")

        for node in found_nodes:
            
            # --- Daten auslesen ---
            node_name = node.name()

            # Ersetze "department" mit dem Namen, den du in Schritt 1 gefunden hast!
            parm_name = "department" 
            
            if node.parm(parm_name):
                # evalAsString() holt den Token (Text) statt des Index, falls es ein Menü ist
                department = node.parm(parm_name).evalAsString()
            else:
                # DEBUG: Falls der Parameter nicht gefunden wird
                self.logger.warning(f"Parameter '{parm_name}' auf Node '{node_name}' nicht gefunden! Verfügbare Parameter: {[p.name() for p in node.parms()]}")
            
            # Label für die GUI bauen
            display_label = f"{department.capitalize()} Layer: {node_name}"
            
            # --- Item erstellen ---
            # WICHTIG: Der Typ "houdini.usd.layer" muss exakt mit deiner YAML matchen!
            item = parent_item.create_item(
                "houdini.usd.layer", 
                "USD Layer Export", 
                display_label
            )
            
            icon_path = os.path.join(self.disk_location, os.pardir, "icons", "usd.png")

            # Icon setzen (nimmt das Node Icon)
            item.set_icon_from_path(icon_path)
            
            # --- Properties setzen ---
            # Diese Infos braucht das Plugin später zum Rendern
            item.properties["node_path"] = node.path()
            item.properties["department"] = department
            item.properties["hda_name"] = hda_name
            
            self.logger.info(f"  + Item erstellt: {display_label}")


    def collect_current_houdini_session(self, settings, parent_item):
        """
        Creates an item that represents the current houdini session.
        """
        publisher = self.parent
        path = hou.hipFile.path()

        if path:
            file_info = publisher.util.get_file_path_components(path)
            display_name = file_info["filename"]
        else:
            display_name = "Current Houdini Session"

        session_item = parent_item.create_item(
            "houdini.session", "Houdini File", display_name
        )

        icon_path = os.path.join(self.disk_location, os.pardir, "icons", "houdini.png")
        session_item.set_icon_from_path(icon_path)

        work_template_setting = settings.get("Work Template")
        if work_template_setting:
            work_template = publisher.engine.get_template_by_name(
                work_template_setting.value
            )
            session_item.properties["work_template"] = work_template

        return session_item