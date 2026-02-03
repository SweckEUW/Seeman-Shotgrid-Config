# The collector hook handles processing the current user’s session to identify what will be published. 
# It also handles processing any file paths that have been dragged/dropped onto the Publisher or added manually via the Publish API. 
# Once the collector identifies what is to be published, Publish Item instances are created within the tree and presented to the user.
# https://developers.shotgridsoftware.com/tk-multi-publish2/customizing.html#

import os
import hou
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()

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

    def process_current_session(self, settings, parent_item) -> None:
        """
        This method analyzes the current engine session and creates a hierarchy of items for publishing.
        """
        
        # create an item representing the current houdini session
        session_item = self.collect_current_houdini_session(settings, parent_item)

        # Collect Seacarus Layer Exporter
        self.collect_seacarus_layers(session_item)


    def collect_seacarus_layers(self, parent_item) -> None:
        """
        Looking for 'seacarus_layer_exporter' Nodes.
        """

        # Looking for all 'seacarus_layer_exporter' Nodes in the LOP context
        hda_name = "seacarus_layer_exporter"
        node_type = hou.nodeType(hou.lopNodeTypeCategory(), hda_name)

        found_nodes:list[hou.Node] = []
        if node_type:
            found_nodes = list(node_type.instances())

        # Loop through all 'seacarus_layer_exporter' Nodes and create items
        for node in found_nodes:
            node_name = node.name()

            item = parent_item.create_item(
                "houdini.usd.layer", 
                "USD Layer Export", 
                node_name
            )

            # Configure item properties. 
            item.properties["node_path"] = node.path()

            icon_path = os.path.join(self.disk_location, os.pardir, "icons", "usd.png")
            item.set_icon_from_path(icon_path)

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