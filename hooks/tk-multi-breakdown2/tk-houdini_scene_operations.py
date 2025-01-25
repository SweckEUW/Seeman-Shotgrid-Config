# Copyright (c) 2021 Autodesk, Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Autodesk, Inc.

import os
import sgtk
import hou
import re

HookBaseClass = sgtk.get_hook_baseclass()


class BreakdownSceneOperations(HookBaseClass):
    """
    Breakdown operations for Houdini.

    This implementation handles detection of alembic node paths.
    """

    def scan_scene(self):
        """
        The scan scene method is executed once at startup and its purpose is
        to analyze the current scene and return a list of references that are
        to be potentially operated on.

        The return data structure is a list of dictionaries. Each scene reference
        that is returned should be represented by a dictionary with three keys:

        - "node_name": The name of the 'node' that is to be operated on. Most DCCs have
          a concept of a node, path or some other way to address a particular
          object in the scene.
        - "node_type": The object type that this is. This is later passed to the
          update method so that it knows how to handle the object.
        - "path": Path on disk to the referenced object.
        - "extra_data": Optional key to pass some extra data to the update method
          in case we'd like to access them when updating the nodes.

        Toolkit will scan the list of items, see if any of the objects matches
        a published file and try to determine if there is a more recent version
        available. Any such versions are then displayed in the UI as out of date.
        """


        items = []

        # get a list of all regular alembic nodes in the file
        alembic_nodes = hou.nodeType(hou.sopNodeTypeCategory(), "alembic").instances()

        # get a tuple of all regular file nodes in the file
        file_nodes_unfiltered = hou.nodeType(
            hou.sopNodeTypeCategory(), "file"
        ).instances()

        reference_nodes = hou.nodeType(
            hou.lopNodeTypeCategory(), "reference::2.0"
        ).instances()

        sublayer_nodes = hou.nodeType(hou.lopNodeTypeCategory(), "sublayer").instances()

        materialx_image_nodes = hou.nodeType(
            hou.vopNodeTypeCategory(), "mtlximage"
        ).instances()

        # refine tuple of all regular file nodes to exclude file nodes inside locked digital asset
        file_nodes = tuple(
            file_node
            for file_node in file_nodes_unfiltered
            if not file_node.isInsideLockedHDA()
        )

        # return an item for each alembic node found. the breakdown app will check
        # the paths of each looking for a template match and a newer version
        for alembic_node in alembic_nodes:

            file_parm = alembic_node.parm("fileName")
            file_path = os.path.normpath(file_parm.eval())

            items.append(
                {"node_name": alembic_node.path(), "node_type": "alembic", "path": file_path}
            )

        # return an item for each file node found. the breakdown app will check
        # the paths of each looking for a template match and a newer version

        for file_node in file_nodes:

            file_parm = file_node.parm("file")
            file_path = os.path.normpath(file_parm.eval())

            items.append({"node_name": file_node.path(), "node_type": "file", "path": file_path})

        # search in all reference node
        for reference_node in reference_nodes:
            file_parm = reference_node.parm("filepath1")
            file_path = os.path.normpath(file_parm.eval())

            items.append(
                {"node_name": reference_node.path(), "node_type": "reference", "path": file_path}
            )

        # search in all sublayer node
        for sublayer_node in sublayer_nodes:
            file_parm = sublayer_node.parm("filepath1")
            file_path = os.path.normpath(file_parm.eval())

            items.append(
                {"node_name": sublayer_node.path(), "node_type": "sublayer", "path": file_path}
            )

        for materialx_image_node in materialx_image_nodes:
            file_parm = materialx_image_node.parm("file")
            file_path = os.path.normpath(file_parm.eval())

            items.append(
                {
                    "node_name": materialx_image_node.path(),
                    "node_type": "materialx_image",
                    "path": file_path,
                }
            )

            items.append(
                {
                    "node_name": materialx_image_node.path(),
                    "node_type": "materialx_image",
                    "path": os.path.dirname(file_path),
                }
            )

        return items
    

    def update(self, item):
        """
        Perform replacements given a number of scene items passed from the app.

        Once a selection has been performed in the main UI and the user clicks
        the update button, this method is called.

        :param item: Dictionary on the same form as was generated by the scan_scene hook above.
                     The path key now holds the path that the node should be updated *to* rather than the current path.
        """

        engine = self.parent.engine

        # these items are to be updated. swap out the fileName parm value with the
        # new path as supplied by the breakdown app.
        node_name = item["node_name"]
        node_type = item["node_type"]
        file_path = item["path"]

        file_path = file_path.replace("\\", "/")

        # update the alembic fileName parm to the new path
        if node_type == "alembic":

            alembic_node = hou.node(node_name)
            engine.log_debug(
                "Updating alembic node '%s' to: %s" % (node_name, file_path)
            )
            alembic_node.parm("fileName").set(file_path)

        # update the file node file parameter to the new path
        if node_type == "file":
            frame_pattern_path = re.compile("(%0(\d)d)")
            frame_match_path = re.search(frame_pattern_path, file_path)

            if frame_match_path:
                full_frame_spec = frame_match_path.group(1)
                padding = frame_match_path.group(2)
                file_path = file_path.replace(full_frame_spec, "$F%s" % (padding,))

            file_node = hou.node(node_name)
            engine.log_debug(
                "Updating file node '%s' to: %s" % (node_name, file_path)
            )
            file_node.parm("file").set(file_path)

        # update the reference node paramter to the new path
        if node_type == "reference":
            reference_node = hou.node(node_name)
            engine.log_debug(
                "Updating file node '%s' to: %s" % (node_name, file_path)
            )
            reference_node.parm("filepath1").set(file_path)

        # update the sublayer node paramter to the new path
        if node_type == "sublayer":
            sublayer_node = hou.node(node_name)
            engine.log_debug(
                "Updating file node '%s' to: %s" % (node_name, file_path)
            )
            sublayer_node.parm("filepath1").set(file_path)

        if node_type == "materialx_image":
            materialx_image_node = hou.node(node_name)
            engine.log_debug(
                "Updating materialx image node '%s' to: %s" % (node_name, file_path)
            )

            if os.path.isfile(file_path):
                materialx_image_node.parm("file").set(file_path)

            else:
                old_path = os.path.normpath(
                    materialx_image_node.parm("file").eval()
                )
                old_path_basename = os.path.basename(old_path)
                materialx_image_node.parm("file").set(
                    f"{file_path}/{old_path_basename}"
                )