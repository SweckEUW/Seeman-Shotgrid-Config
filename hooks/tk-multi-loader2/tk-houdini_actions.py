# Copyright (c) 2015 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
import hou
import os

HookBaseClass = sgtk.get_hook_baseclass()

class HoudiniActions(HookBaseClass):
    """
    Hook that loads defined actions into the loader UI for Houdini.
    """

    # --------------------------------------------------------------------------
    # USER CONFIGURATION - BITTE HIER ANPASSEN
    # --------------------------------------------------------------------------
    
    # 1. Der interne Name deines HDAs (so wie er in Houdini unter "Operator Type Manager" steht)
    # Beispiel: "my_studio::asset_loader::1.0"
    HDA_NODE_TYPE = "my_studio::asset_loader::1.0" 

    # 2. Welcher Node-Name soll im Stage erzeugt werden?
    HDA_NODE_NAME = "LOAD_ASSET"

    # 3. Wie heißen deine Steps in ShotGrid? -> Wie heißen die Parameter im HDA?
    # Links (Key): ShotGrid Step Name (Case Sensitive! Muss exakt stimmen)
    # Rechts (Value): Prefix im HDA (z.B. "model" sucht nach "model_path" und "load_model")
    DEPT_MAPPING = {
        "Modeling": "model",
        "Surfacing": "surface",
        "Groom": "groom",
        "Rigging": "anim" 
    }

    # 4. Nach welchem File-Type soll in ShotGrid gesucht werden?
    # Schau in ShotGrid unter "Admin Menu -> Entities -> Published Files" nach.
    # Oft "USD Asset", "USD File" oder "Alembic Cache".
    TARGET_FILE_TYPE = "USD Asset"

    # --------------------------------------------------------------------------
    # ACTION REGISTRATION
    # --------------------------------------------------------------------------

    def generate_actions(self, sg_publish_data, actions, ui_area):
        action_instances = []

        if "reference" in actions:
            action_instances.append(
                {"name": "reference", "params": None, "caption": "Create Reference", "description": "References the item."}
            )

        return action_instances

    def execute_multiple_actions(self, actions):
        for single_action in actions:
            self.execute_action(single_action["name"], single_action["params"], single_action["sg_publish_data"])

    def execute_action(self, name, params, sg_publish_data):
        # resolve path
        path = self.get_publish_path(sg_publish_data)

        if name == "reference":
            self.load_smart_asset_hda(path, sg_publish_data)

    # --------------------------------------------------------------------------
    # ACTION EXECUTION (THE LOGIC)
    # --------------------------------------------------------------------------

    def load_smart_asset_hda(self, sg_publish_data, publish_ids, current_selection):
        """
        Main logic loop. Queries ShotGrid for the latest Dept files and builds the HDA.
        """
        
        # 1. Check Context
        # ----------------
        # Wir müssen sicherstellen, dass wir im LOP (Solaris) Context sind
        # Da wir Nodes erstellen wollen, ist /stage der sicherste Ort.
        stage_root = hou.node("/stage")
        if not stage_root:
            # Versuch, einen LOP Network zu finden oder User warnen
            editors = [p for p in hou.networkPaneEditors() if p.pwd().childTypeCategory() == hou.lopNodeTypeCategory()]
            if editors:
                stage_root = editors[0].pwd()
            else:
                hou.ui.displayMessage("Bitte öffne einen Solaris (LOP) Context oder gehe nach /stage.")
                return

        # 2. ShotGrid Verbindung & Entity finden
        # --------------------------------------
        engine = sgtk.platform.current_engine()
        sg = engine.shotgun

        # Das Entity (das Asset), das angeklickt wurde
        entity = sg_publish_data.get("entity")
        if not entity:
            hou.ui.displayMessage("Fehler: Dieser Publish ist keinem Asset zugeordnet (Link fehlt).")
            return
        
        asset_name = entity.get("name", "Asset")
        self.logger.info(f"Starte Smart-Load für Asset: {asset_name}")

        # 3. Query: Finde ALLE Publishes für dieses Asset
        # -----------------------------------------------
        # Wir filtern nach Asset und File-Type. 
        # Wir holen absichtlich ALLES, um sicherzustellen, dass wir wirklich das neuste finden.
        
        filters = [
            ["entity", "is", entity],
            ["published_file_type", "name_is", self.TARGET_FILE_TYPE],
            ["task", "is_not", None] # Ignoriere Publishes ohne Task
        ]
        
        fields = ["path", "version_number", "task", "step", "name"]
        
        # Sortieren: Version absteigend (Höchste Version zuerst)
        order = [{"field_name": "version_number", "direction": "desc"}]
        
        try:
            all_publishes = sg.find("PublishedFile", filters, fields, order)
        except Exception as e:
            hou.ui.displayMessage(f"ShotGrid Query Fehler: {e}")
            return

        # 4. Filterung: Nur der erste Treffer pro Department gewinnt
        # ----------------------------------------------------------
        latest_paths = {}

        for pub in all_publishes:
            # Step Name herausfinden (manchmal direkt im Step Feld, manchmal via Task)
            step_name = None
            if pub.get("step"):
                step_name = pub["step"].get("name")
            elif pub.get("task"):
                # Fallback: Wenn Step nicht direkt da ist, versuchen wir ihn aus dem Task zu holen (Pipeline dependent)
                # Hier nehmen wir an, dass SG den Step liefert, wenn angefragt.
                pass 

            if not step_name:
                continue

            # Mapping prüfen
            target_prefix = self.DEPT_MAPPING.get(step_name)
            
            # Wenn wir diesen Prefix noch nicht haben -> Speichern (da sortiert = neuste Version)
            if target_prefix and target_prefix not in latest_paths:
                
                # Pfad extrahieren
                raw_path = pub.get("path", {})
                local_file_path = self.get_local_path(raw_path)

                if local_file_path:
                    # Pfad für Houdini lesbar machen (Forward Slashes)
                    latest_paths[target_prefix] = local_file_path.replace("\\", "/")
                    self.logger.info(f"  -> Found {step_name} v{pub['version_number']}")

        # 5. Houdini Node Erstellung
        # --------------------------
        try:
            # Node erstellen
            loader = stage_root.createNode(self.HDA_NODE_TYPE, node_name=f"{self.HDA_NODE_NAME}_{asset_name}")
        except hou.OperationFailed:
            hou.ui.displayMessage(f"Konnte HDA '{self.HDA_NODE_TYPE}' nicht erstellen.\nBitte prüfe, ob die HDA Library geladen ist.")
            return

        # Asset Name Parameter setzen (wenn vorhanden)
        pt = loader.parm("asset_name")
        if pt:
            pt.set(asset_name)

        # 6. Parameter befüllen
        # ---------------------
        # Wir iterieren durch unser Mapping und schauen, was wir gefunden haben
        for step, prefix in self.DEPT_MAPPING.items():
            
            path_found = latest_paths.get(prefix)
            
            # Parameter Objekte holen
            parm_path = loader.parm(f"{prefix}_path")  # z.B. model_path
            parm_toggle = loader.parm(f"load_{prefix}") # z.B. load_model
            
            if parm_path and parm_toggle:
                if path_found:
                    # Pfad setzen
                    parm_path.set(path_found)
                    # Aktivieren
                    parm_toggle.set(1)
                else:
                    # Nichts gefunden -> Deaktivieren (Muting)
                    parm_toggle.set(0)
                    self.logger.info(f"  -> No publish found for {step}, disabling toggle.")

        # 7. UI Cleanup
        loader.moveToGoodPosition()
        loader.setSelected(True)

    def load_sublayer(self, sg_publish_data, publish_ids, current_selection):
        """
        Fallback Action: Simple Sublayer import (wie Maya Reference).
        """
        stage_root = hou.node("/stage")
        if not stage_root: return

        path = self.get_local_path(sg_publish_data.get("path"))
        if not path: return
        
        path = path.replace("\\", "/")
        name = sg_publish_data.get("code", "import")
        
        sublayer = stage_root.createNode("sublayer", node_name=name)
        sublayer.parm("filepath1").set(path)
        sublayer.moveToGoodPosition()
        sublayer.setSelected(True)

    # --------------------------------------------------------------------------
    # HELPER
    # --------------------------------------------------------------------------

    def get_local_path(self, path_dict):
        """
        Helper to extract the OS-specific path from the SG path dictionary.
        """
        if not path_dict:
            return None
            
        if os.name == "nt":
            return path_dict.get("local_path_windows")
        elif os.name == "posix":
            # Unterscheidung Mac/Linux
            import sys
            if sys.platform == "darwin":
                return path_dict.get("local_path_mac")
            else:
                return path_dict.get("local_path_linux")
        return None