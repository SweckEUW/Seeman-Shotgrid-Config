# Copyright (c) 2015 Shotgun Software Inc.

import os
import re
import sgtk
import maya.cmds as cmds
import maya.mel as mel
import mayaUsd.lib
import os
import re

HookBaseClass = sgtk.get_hook_baseclass()

class MayaActions(HookBaseClass):

    def generate_actions(self, sg_publish_data, actions, ui_area):
        action_instances = []

        if "reference" in actions:
            action_instances.append(
                {"name": "reference", "params": None, "caption": "Create Reference", "description": "References the item."}
            )

        if "import" in actions:
            action_instances.append(
                {"name": "import", "params": None, "caption": "Import into Scene", "description": "Imports the item."}
            )

        return action_instances

    def execute_multiple_actions(self, actions):
        for single_action in actions:
            self.execute_action(single_action["name"], single_action["params"], single_action["sg_publish_data"])

    def execute_action(self, name, params, sg_publish_data):
        # resolve path
        path = self.get_publish_path(sg_publish_data)

        if name == "reference":
            self._reference(path, sg_publish_data)

        if name == "import":
            self._import(path, sg_publish_data)

    # ----------------------------------------------------------------------------------------
    # HELPER METHODS
    # ----------------------------------------------------------------------------------------

    def _reference(self, path, sg_publish_data):
        """
        Intelligente Reference Funktion.
        Entscheidet basierend auf Dateityp, was zu tun ist.
        """
        if not os.path.exists(path):
            raise Exception("File not found on disk - '%s'" % path)

        # 1. USD CHECK: Ist es eine USD Datei?
        # Wenn ja, nutzen wir NICHT Maya Reference, sondern Proxy Shape (das ist der moderne Reference Workflow)
        if path.lower().endswith((".usd", ".usda", ".usdc")):
            self.parent.log_info("USD file detected during Reference action. Switching to Proxy Shape loader.")
            self._create_usd_proxy_shape(path, sg_publish_data)
            return

        # 2. NAMESPACE CLEANUP
        # Erstelle Namespace aus Entity + Name
        raw_namespace = "%s_%s" % (
            sg_publish_data.get("entity", {}).get("name", "Asset"),
            sg_publish_data.get("name", "Publish"),
        )
        
        # WICHTIG: Entferne alle illegalen Zeichen (Klammern, Leerzeichen etc.)
        # Erlaubt sind nur a-z, A-Z, 0-9 und _
        namespace = re.sub(r'[^a-zA-Z0-9_]', '_', raw_namespace)
        
        # Doppelte Unterstriche entfernen (Kosmetik)
        namespace = re.sub(r'_{2,}', '_', namespace)

        # 3. STANDARD MAYA REFERENCE (.ma, .mb, .abc)
        cmds.file(
            path,
            reference=True,
            loadReferenceDepth="all",
            mergeNamespacesOnClash=False,
            namespace=namespace,
            returnNewNodes=True,
            ignoreVersion=True,
        )

    def _create_usd_proxy_shape(self, path, sg_publish_data):
        """
        Sucht die erste USD Stage und fügt das Asset KORREKT unter dem DefaultPrim (Shot) ein.
        """
        app = self.parent
        
        # 1. Plugin laden
        if not cmds.pluginInfo('mayaUsdPlugin', query=True, loaded=True):
            try:
                cmds.loadPlugin('mayaUsdPlugin')
            except Exception:
                app.log_error("Could not load mayaUsdPlugin.")
                return

        # 2. Stage finden (Alle suchen, erste nehmen)
        all_stages = cmds.ls(type="mayaUsdProxyShape", long=True)
        
        if not all_stages:
            app.log_error("Keine USD Stage (Proxy Shape) in der Szene gefunden!")
            return

        proxy_shape_node = all_stages[0]
        app.log_info(f"Nutze Stage: {proxy_shape_node}")

        # 3. Stage Objekt holen
        try:
            stage = mayaUsd.lib.GetPrim(proxy_shape_node).GetStage()
        except Exception as e:
            app.log_error(f"Konnte Stage nicht abrufen: {e}")
            return

        # ---------------------------------------------------------------------
        # 4. PFAD BERECHNUNG (HIER IST DER FIX)
        # ---------------------------------------------------------------------
        
        # Standard-Fallback, falls die Stage leer ist
        scope_path = "/Assets" 
        
        # Wir fragen die Stage: "Wer ist dein Chef?" (Default Prim)
        # In deinem Fall ist das "sq010_sh010"
        default_prim = stage.GetDefaultPrim()
        
        if default_prim and default_prim.IsValid():
            # Das gibt uns den Pfad "/sq010_sh010"
            root_path = default_prim.GetPath().pathString
            
            # Wir hängen "/Assets" hinten dran -> "/sq010_sh010/Assets"
            scope_path = f"{root_path}/Assets"
            app.log_info(f"Füge Asset in Default Prim Struktur ein: {scope_path}")
        else:
            app.log_warning("Kein Default Prim gefunden! Erstelle Assets auf Root-Ebene.")

        # ---------------------------------------------------------------------

        # Namen vorbereiten
        raw_name = sg_publish_data.get("code", os.path.basename(path))
        raw_name = os.path.splitext(raw_name)[0]
        asset_name = re.sub(r'[^a-zA-Z0-9_]', '_', raw_name)
        
        usd_file_path = path.replace("\\", "/")

        # 5. Scope definieren (Erstellt /sq010_sh010/Assets falls nötig)
        assets_prim = stage.DefinePrim(scope_path, "Scope")
        
        if not assets_prim.IsValid():
            app.log_error(f"Konnte Scope {scope_path} nicht erstellen.")
            return

        # 6. Eindeutigen Namen finden
        base_asset_path = f"{scope_path}/{asset_name}"
        final_asset_path = base_asset_path
        counter = 1
        
        while stage.GetPrimAtPath(final_asset_path).IsValid():
            final_asset_path = f"{base_asset_path}_{counter}"
            counter += 1

        # 7. Referenz erstellen
        new_prim = stage.DefinePrim(final_asset_path, "Xform")
        
        try:
            references = new_prim.GetReferences()
            references.AddReference(usd_file_path)
            app.log_info(f"Referenz erstellt: {final_asset_path}")
        except Exception as e:
            app.log_error(f"Fehler beim Referenzieren: {e}")

    def _import(self, path, sg_publish_data):
        if not os.path.exists(path):
            raise Exception("File not found on disk - '%s'" % path)
        
        # Auch beim Importieren könnte man für USD eine Sonderbehandlung einbauen,
        # aber cmds.file(i=True) funktioniert für USD meistens (convert to geo),
        # solange das Plugin geladen ist.
        
        cmds.file(path, i=True, returnNewNodes=True)