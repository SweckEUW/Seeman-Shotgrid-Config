# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Hook that loads defines all the available actions, broken down by publish type.
"""

import os
import re
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()


class HoudiniActions(HookBaseClass):
    ##############################################################################################################
    # public interface - to be overridden by deriving classes

    def generate_actions(self, sg_publish_data, actions, ui_area):
        """
        Returns a list of action instances for a particular publish.
        This method is called each time a user clicks a publish somewhere in the UI.
        The data returned from this hook will be used to populate the actions menu for a publish.

        The mapping between Publish types and actions are kept in a different place
        (in the configuration) so at the point when this hook is called, the loader app
        has already established *which* actions are appropriate for this object.

        The hook should return at least one action for each item passed in via the
        actions parameter.

        This method needs to return detailed data for those actions, in the form of a list
        of dictionaries, each with name, params, caption and description keys.

        Because you are operating on a particular publish, you may tailor the output
        (caption, tooltip etc) to contain custom information suitable for this publish.

        The ui_area parameter is a string and indicates where the publish is to be shown.
        - If it will be shown in the main browsing area, "main" is passed.
        - If it will be shown in the details area, "details" is passed.
        - If it will be shown in the history area, "history" is passed.

        Please note that it is perfectly possible to create more than one action "instance" for
        an action! You can for example do scene introspection - if the action passed in
        is "character_attachment" you may for example scan the scene, figure out all the nodes
        where this object can be attached and return a list of action instances:
        "attach to left hand", "attach to right hand" etc. In this case, when more than
        one object is returned for an action, use the params key to pass additional
        data into the run_action hook.

        :param sg_publish_data: Shotgun data dictionary with all the standard publish fields.
        :param actions: List of action strings which have been defined in the app configuration.
        :param ui_area: String denoting the UI Area (see above).
        :returns List of dictionaries, each with keys name, params, caption and description
        """
        app = self.parent
        app.log_debug(
            "Generate actions called for UI element %s. "
            "Actions: %s. Publish Data: %s" % (ui_area, actions, sg_publish_data)
        )

        action_instances = []

        if "merge" in actions:
            action_instances.append(
                {
                    "name": "merge",
                    "params": None,
                    "caption": "Merge",
                    "description": "This will merge the item into the scene.",
                }
            )
        if "file_sop" in actions:
            action_instances.append(
                {
                    "name": "file_sop",
                    "params": None,
                    "caption": "Import as file node",
                    "description": "This will import the item into the scene through a file node.",
                }
            )
        if "import" in actions:
            action_instances.append(
                {
                    "name": "import",
                    "params": None,
                    "caption": "Import",
                    "description": "Import the Alembic cache file into a geometry network.",
                }
            )
        if "stage_import" in actions:
            action_instances.append(
                {
                    "name": "stage_import",
                    "params": None,
                    "caption": "Stage import",
                    "description": "Import the Alembic cache file into the stage.",
                }
            )
        if "file_cop" in actions:
            action_instances.append(
                {
                    "name": "file_cop",
                    "params": None,
                    "caption": "File COP",
                    "description": "Load an image or image sequence via File COP.",
                }
            )

        if "materialx_image" in actions:
            action_instances.append(
                {
                    "name": "materialx_image",
                    "params": None,
                    "caption": "Import as MaterialX image",
                    "description": "Load image in a MaterialX node and add it to stage context.",
                }
            )

        if "materialx_folder" in actions:
            action_instances.append(
                {
                    "name": "materialx_folder",
                    "params": None,
                    "caption": "Import as MaterialX images",
                    "description": "Load texture folder as MaterialX image nodes and add it to stage context.",
                }
            )

        if "component_builder" in actions:
            action_instances.append(
                {
                    "name": "component_builder",
                    "params": None,
                    "caption": "Create component builder",
                    "description": "Creates a configured component builder for shading work.",
                }
            )

        if "usd_reference" in actions:
            action_instances.append(
                {
                    "name": "usd_reference",
                    "params": None,
                    "caption": "Reference",
                    "description": "This will create a reference node in the stage context.",
                }
            )

        if "usd_sublayer" in actions:
            action_instances.append(
                {
                    "name": "usd_sublayer",
                    "params": None,
                    "caption": "Sublayer",
                    "description": "This will create a sublayer node in the stage context.",
                }
            )

        return action_instances

    def execute_multiple_actions(self, actions):
        """
        Executes the specified action on a list of items.

        The default implementation dispatches each item from ``actions`` to
        the ``execute_action`` method.

        The ``actions`` is a list of dictionaries holding all the actions to execute.
        Each entry will have the following values:

            name: Name of the action to execute
            sg_publish_data: Publish information coming from Shotgun
            params: Parameters passed down from the generate_actions hook.

        .. note::
            This is the default entry point for the hook. It reuses the ``execute_action``
            method for backward compatibility with hooks written for the previous
            version of the loader.

        .. note::
            The hook will stop applying the actions on the selection if an error
            is raised midway through.

        :param list actions: Action dictionaries.
        """
        for single_action in actions:
            name = single_action["name"]
            sg_publish_data = single_action["sg_publish_data"]
            params = single_action["params"]
            self.execute_action(name, params, sg_publish_data)

    def execute_action(self, name, params, sg_publish_data):
        """
        Execute a given action. The data sent to this be method will
        represent one of the actions enumerated by the generate_actions method.

        :param name: Action name string representing one of the items returned by generate_actions.
        :param params: Params data, as specified by generate_actions.
        :param sg_publish_data: Shotgun data dictionary with all the standard publish fields.
        :returns: No return value expected.
        """
        app = self.parent
        app.log_debug(
            "Execute action called for action %s. "
            "Parameters: %s. Publish Data: %s" % (name, params, sg_publish_data)
        )

        # resolve path
        path = self.get_publish_path(sg_publish_data)

        if name == "merge":
            self._merge(path, sg_publish_data)

        if name == "file_sop":
            self._file_sop(path, sg_publish_data)

        if name == "materialx_image":
            self._materialx_image(path, sg_publish_data)

        if name == "materialx_folder":
            self._materialx_folder(path, sg_publish_data)

        if name == "component_builder":
            self._component_builder(path, sg_publish_data)

        if name == "usd_reference":
            self._usd_reference(path, sg_publish_data)

        if name == "usd_sublayer":
            self._usd_sublayer(path, sg_publish_data)

        if name == "import":
            self._import(path, sg_publish_data)

        if name == "stage_import":
            self._stage_import(path, sg_publish_data)

        if name == "file_cop":
            self._file_cop(path, sg_publish_data)

    ##############################################################################################################
    # helper methods which can be subclassed in custom hooks to fine tune the behaviour of things

    def _merge(self, path, sg_publish_data):
        """
        Merge a published hip file into the working hip file with
        the default settings Houdini would use if you did it in the UI.

        :param path: Path to file.
        :param sg_publish_data: Shotgun data dictionary with all the standard publish fields.
        """
        import hou

        if not os.path.exists(path):
            raise Exception("File not found on disk - '%s'" % path)

        # use the default settings, which tries to merge all nodes
        # and is conservative about overwriting and errors
        #
        # NOTE: We're ensuring that the path uses forward-slash separators
        # since some hearly H17 builds had major issues with backslashes on
        # Windows.
        hou.hipFile.merge(
            path.replace(os.path.sep, "/"),
            node_pattern="*",
            overwrite_on_conflict=False,
            ignore_load_warnings=False,
        )

    ##############################################################################################################
    def _import(self, path, sg_publish_data):
        """Import the supplied path as a geo/alembic sop.

        :param str path: The path to the file to import.
        :param dict sg_publish_data: The publish data for the supplied path.

        """

        import hou

        app = self.parent

        name = sg_publish_data.get("name", "alembic")
        path = self.get_publish_path(sg_publish_data)

        # houdini doesn't like UNC paths.
        path = path.replace("\\", "/")

        obj_context = _get_current_context("/obj")

        try:
            geo_node = obj_context.createNode("geo", name)
        except hou.OperationFailed:
            # failed to create the node in this context, create at top-level
            obj_context = hou.node("/obj")
            geo_node = obj_context.createNode("geo", name)

        app.log_debug("Created geo node: %s" % (geo_node.path(),))

        # delete the default nodes created in the geo
        for child in geo_node.children():
            child.destroy()

        alembic_sop = geo_node.createNode("alembic", name)
        alembic_sop.parm("fileName").set(path)
        app.log_debug(
            "Creating alembic sop: %s\n  path: '%s' " % (alembic_sop.path(), path)
        )
        alembic_sop.parm("reload").pressButton()

        _show_node(alembic_sop)

    ##############################################################################################################

    def _stage_import(self, path, sg_publish_data):
        """Import the supplied path as a geo/alembic sop.

        :param str path: The path to the file to import.
        :param dict sg_publish_data: The publish data for the supplied path.

        """

        import hou

        name = sg_publish_data.get("name", "alembic")
        path = self.get_publish_path(sg_publish_data)

        # houdini doesn't like UNC paths.
        path = path.replace("\\", "/")

        stage = hou.node("/stage")

        sop_create_node = stage.createNode("sopcreate", name)
        sop_create_node.allowEditingOfContents()

        alembic_node = (
            sop_create_node.node("sopnet").node("create").createNode("alembic", name)
        )
        alembic_node.parm("fileName").set(path)
        alembic_node.parm("reload").pressButton()

        try:
            _show_node(sop_create_node)
        except UnboundLocalError:
            pass

    def _file_sop(self, path, sg_publish_data):
        """Import the supplied path as a file sop.

        :param str path: The path to the file to import.
        :param dict sg_publish_data: The publish data for the supplied path.

        """

        import hou

        app = self.parent

        frame_pattern = re.compile("(%0(\d)d)")
        frame_pattern_name = re.compile("([^.]+)")
        frame_pattern_name_version = re.compile("_v\d{3}")

        name = sg_publish_data.get("name")
        path = self.get_publish_path(sg_publish_data)

        frame_match = re.search(frame_pattern, path)
        if frame_match:
            full_frame_spec = frame_match.group(1)
            padding = frame_match.group(2)
            path = path.replace(full_frame_spec, "$F%s" % (padding,))

        frame_match_name = re.search(frame_pattern_name, name)
        if frame_match_name:
            name = frame_match_name.group(0)

        frame_match_name_version = re.search(frame_pattern_name_version, name)
        if frame_match_name_version:
            name = name.replace(frame_match_name_version.group(0), "")

        self.logger.info(name)

        # houdini doesn't like UNC paths.
        path = path.replace("\\", "/")

        obj_context = _get_current_context("/obj")

        try:
            geo_node = obj_context.createNode("geo", name)
        except hou.OperationFailed:
            # failed to create the node in this context, create at top-level
            obj_context = hou.node("/obj")
            geo_node = obj_context.createNode("geo", name)

        app.log_debug("Created geo node: %s" % (geo_node.path(),))

        # delete the default nodes created in the geo
        for child in geo_node.children():
            child.destroy()

        file_sop = geo_node.createNode("file", name)
        file_sop.parm("file").set(path)
        app.log_info("Creating file sop: %s\n  path: '%s' " % (file_sop.path(), path))
        file_sop.parm("reload").pressButton()

        _show_node(file_sop)

    def _usd_reference(self, path, sg_publish_data):
        # Import a USD file into a reference node in the stage context

        import hou

        asset_name = sg_publish_data.get("entity").get("name")
        task = sg_publish_data.get("task").get("name")

        name = asset_name + "_" + task
        name = name.replace(" ", "_")

        path = self.get_publish_path(sg_publish_data)

        self.logger.info(name)

        # houdini doesn't like UNC paths.
        path = path.replace("\\", "/")

        # Set stage
        stage_context = hou.node("/stage")

        # Create node
        reference_node = stage_context.createNode("reference", name)

        # Set parameters
        reference_node.parm("primpath1").set(
            sg_publish_data.get("name").replace("-", "_")
        )
        reference_node.parm("filepath1").set(path)
        reference_node.parm("primpath").set("/scene/$OS")
        reference_node.parm("primkind").set("group")
        reference_node.parm("reftype").set("payload")

        reference_node.parm("reload").pressButton()

        _show_node(reference_node)

    def _materialx_image(self, path, sg_publish_data):
        # Import a texture file into a materialx image node
        asset_name = sg_publish_data.get("entity").get("name")
        task = sg_publish_data.get("task").get("name")

        name = asset_name + "_" + task
        name = name.replace(" ", "_")

        path = self.get_publish_path(sg_publish_data)

        self.logger.info(name)

        # houdini doesn't like UNC paths.
        path = path.replace("\\", "/")

        material_node = _material_selection_menu()
        if not material_node:
            return

        image_node = material_node.createNode(
            "mtlximage", sg_publish_data.get("code").split(" ")[0]
        )
        image_node.parm("file").set(path)

        _show_node(image_node)

    def _materialx_folder(self, path, sg_publish_data):
        # Imports texture folder as materialx image nodes
        import hou

        file_paths_to_load = []
        for file in os.listdir(path):
            if os.path.splitext(file)[1] != ".exr":
                continue

            if file.count(".") == 2:
                new_filename = f"{file.split('.')[0]}.<UDIM>.{file.split('.')[2]}"
            else:
                new_filename = file

            if os.path.join(path, new_filename) not in file_paths_to_load:
                file_paths_to_load.append(os.path.join(path, new_filename))

        material_node = _material_selection_menu()
        if not material_node:
            return

        if len(file_paths_to_load) == 0:
            hou.ui.displayMessage(
                "No .EXR files found in the folder. Did you publish .EXR files or something else?",
                severity=hou.severityType.Error,
            )
            return

        new_image_nodes = []
        for file_path in file_paths_to_load:
            # Hotfix for odd filenames we sometimes get
            new_node_name = (
                os.path.basename(file_path)
                .split(".")[0]
                .replace(" ", "")
                .replace("-", "")
            )

            image_node = material_node.createNode("mtlximage", new_node_name)
            image_node.parm("file").set(file_path.replace("\\", "/"))
            new_image_nodes.append(image_node)

        material_node.layoutChildren()
        _show_node(image_node)

        automatic_texture_add_choice = hou.ui.displayMessage(
            "Automatically add the textures to correct input? Note: This might not work for all maps.",
            ("Yes", "No"),
        )

        # Goes by index of buttons, so 1 would actually match "no"
        if automatic_texture_add_choice:
            return

        mtlxstandard_surface_node = material_node.node("mtlxstandard_surface")
        if not mtlxstandard_surface_node:
            hou.ui.displayMessage(
                "Could not find a MaterialX Standard Surface node to automatically add the textures to.",
                severity=hou.severityType.Error,
            )
            return

        for image_node in new_image_nodes:
            if "Alpha" in image_node.name():
                mtlxstandard_surface_node.setNamedInput("opacity", image_node, "out")

            elif "BaseColor" in image_node.name() or "Base Color" in image_node.name():
                mtlxstandard_surface_node.setNamedInput("base_color", image_node, "out")

            elif "Displacement" in image_node.name():
                image_node.parm("signature").set("default")
                if material_node.node("mtlxdisplacement"):
                    mtlxrange_node = material_node.createNode("mtlxrange")
                    mtlxrange_node.setNamedInput("in", image_node, "out")
                    mtlxrange_node.parm("outlow").set(-0.5)
                    mtlxrange_node.parm("outhigh").set(0.5)
                    material_node.node("mtlxdisplacement").setNamedInput(
                        "displacement", mtlxrange_node, "out"
                    )
                else:
                    hou.ui.displayMessage(
                        "Could not find a MaterialX Displacement node to add displacement to. Skipping.",
                        severity=hou.severityType.Error,
                    )

            elif "Emission" in image_node.name():
                image_node.parm("signature").set("default")
                mtlxstandard_surface_node.setNamedInput("emission", image_node, "out")

            elif "Metallic" in image_node.name():
                image_node.parm("signature").set("default")
                mtlxstandard_surface_node.setNamedInput("metalness", image_node, "out")

            elif "Normal" in image_node.name():
                image_node.parm("signature").set("vector3")
                mtlxnormalmap_node = material_node.createNode("mtlxnormalmap")
                mtlxnormalmap_node.setNamedInput("in", image_node, "out")
                mtlxstandard_surface_node.setNamedInput(
                    "normal", mtlxnormalmap_node, "out"
                )

            elif "Roughness" in image_node.name():
                image_node.parm("signature").set("default")
                mtlxstandard_surface_node.setNamedInput(
                    "specular_roughness", image_node, "out"
                )

            elif "Specular" in image_node.name():
                image_node.parm("signature").set("default")
                mtlxstandard_surface_node.setNamedInput("specular", image_node, "out")

            else:
                hou.ui.displayMessage(
                    f"Could not automatically match {image_node.name()}. Please configure it yourself.",
                    severity=hou.severityType.Error,
                )

        material_node.layoutChildren()

    def _component_builder(self, path, sg_publish_data):
        # Creates a configured component builder for an alembic file
        import hou

        asset_name = sg_publish_data.get("entity").get("name")
        task = sg_publish_data.get("task").get("name")

        name = asset_name + "_" + task
        name = name.replace(" ", "_")

        path = self.get_publish_path(sg_publish_data)

        self.logger.info(name)

        # houdini doesn't like UNC paths.
        path = path.replace("\\", "/")

        stage = hou.node("/stage")

        component_geometry_node = stage.createNode(
            "componentgeometry",
            f'{sg_publish_data.get("name").replace("-", "")}_geometry',
        )
        material_library = stage.createNode("materiallibrary")

        component_material_node = stage.createNode(
            "componentmaterial",
            f'{sg_publish_data.get("name").replace("-", "")}_material',
        )
        component_output_node = stage.createNode(
            "componentoutput", f'{sg_publish_data.get("name").replace("-", "")}'
        )
        sgtk_usd_rop_node = stage.createNode("sgtk_usd_rop")

        component_material_node.setInput(0, component_geometry_node)
        component_material_node.setInput(1, material_library)
        component_output_node.setInput(0, component_material_node)
        sgtk_usd_rop_node.setInput(0, component_output_node)

        stage.layoutChildren(
            (
                component_geometry_node,
                material_library,
                component_material_node,
                component_output_node,
                sgtk_usd_rop_node,
            )
        )

        file_node = (
            component_geometry_node.node("sopnet").node("geo").createNode("file")
        )
        file_node.parm("file").set(path)
        component_geometry_node.node("sopnet").node("geo").node("default").setInput(
            0, file_node
        )
        component_output_node.parm("localize").set(False)

        sticky_note = stage.createStickyNote()
        sticky_note.setText(
            """1. Create your materials in the materiallibrary node.

2. Import the textures using the ShotGrid loader.

3. Assign the materials to your model (this tutorial might help: https://youtu.be/vg754CDMElI).
            
4. Once your shading work is done, click 'save to disk' on the sgtk_usd_rop. 

5. Publish the USD file with the ShotGrid publisher."""
        )
        sticky_note.move((5, 0))
        sticky_note.setSize((5, 4))

        try:
            _show_node(sgtk_usd_rop_node)
        except UnboundLocalError:
            pass

    def _usd_sublayer(self, path, sg_publish_data):
        # Import a USD file into a sublayer node in the stage context

        import hou

        asset_name = sg_publish_data.get("entity").get("name")
        task = sg_publish_data.get("task").get("name")

        name = asset_name + "_" + task
        name = name.replace(" ", "_")

        path = self.get_publish_path(sg_publish_data)

        self.logger.info(name)

        # houdini doesn't like UNC paths.
        path = path.replace("\\", "/")

        # Set stage
        stage_context = hou.node("/stage")

        # Create node
        sublayer_node = stage_context.createNode("sublayer", name)

        # Set parameters
        sublayer_node.parm("filepath1").set(path)

        sublayer_node.parm("reload").pressButton()

        _show_node(sublayer_node)

    ##############################################################################################################

    def _file_cop(self, path, sg_publish_data):
        """Read the supplied path as a file COP.

        :param str path: The path to the file to import.
        :param dict sg_publish_data: The publish data for the supplied path.

        """

        import hou

        app = self.parent

        publish_name = sg_publish_data.get("name", "published_file")

        # we'll use the publish name for the file cop node name, but we need to
        # remove non alphanumeric characers from the string (houdini node names
        # must be alphanumeric). first, build a regex to match non alpha-numeric
        # characters. Then use it to replace any matches with an underscore

        # cannot use special characters to create nodes
        pattern = re.compile("[\W_]+")
        publish_name = pattern.sub("_", publish_name)

        # get the publish path
        path = self.get_publish_path(sg_publish_data)

        # houdini doesn't like UNC paths.
        path = path.replace("\\", "/")

        img_context = _get_current_context("/img")

        try:
            file_cop = img_context.createNode("file", publish_name)
        except hou.OperationFailed:
            # failed to create the node in the current context.
            img_context = hou.node("/img")

            comps = [c for c in img_context.children() if c.type().name() == "img"]

            if comps:
                # if there are comp networks, just pick the first one
                img_network = comps[0]
            else:
                # if not, create one at the /img and then add the file cop
                img_network = img_context.createNode("img", "comp1")

            file_cop = img_network.createNode("file", publish_name)

        # replace any %0#d format string with the corresponding houdini frame
        # env variable. example %04d => $F4
        frame_pattern = re.compile("(%0(\d)d)")
        frame_match = re.search(frame_pattern, path)
        if frame_match:
            full_frame_spec = frame_match.group(1)
            padding = frame_match.group(2)
            path = path.replace(full_frame_spec, "$F%s" % (padding,))

        file_cop.parm("filename1").set(path)
        app.log_debug("Created file COP: %s\n  path: '%s' " % (file_cop.path(), path))
        file_cop.parm("reload").pressButton()

        _show_node(file_cop)


##############################################################################################################
def _get_current_context(context_type):
    """Attempts to return the current node context.

    :param str context_type: Return a full context under this context type.
        Example: "/obj"

    Looks for a current network pane tab displaying the supplied context type.
    Returns the full context being displayed in that network editor.

    """

    import hou

    # default to the top level context type
    context = hou.node(context_type)

    network_tab = _get_current_network_panetab(context_type)
    if network_tab:
        context = network_tab.pwd()

    return context


##############################################################################################################
def _get_current_network_panetab(context_type):
    """Attempt to retrieve the current network pane tab.

    :param str context_type: Search for a network pane showing this context
        type. Example: "/obj"

    """

    import hou

    network_tab = None

    # there doesn't seem to be a way to know the current context "type" since
    # there could be multiple network panels open with different contexts
    # displayed. so for now, loop over pane tabs and find a network editor in
    # the specified context type that is the current tab in its pane. hopefully
    # that's the one the user is looking at.
    for panetab in hou.ui.paneTabs():
        if (
            isinstance(panetab, hou.NetworkEditor)
            and panetab.pwd().path().startswith(context_type)
            and panetab.isCurrentTab()
        ):
            network_tab = panetab
            break

    return network_tab


##############################################################################################################
def _show_node(node):
    """Frame the supplied node in the current network pane.

    :param hou.Node node: The node to frame in the current network pane.

    """

    context_type = "/" + node.path().split("/")[0]
    network_tab = _get_current_network_panetab(context_type)

    if not network_tab:
        return

    # select the node and frame it
    node.setSelected(True, clear_all_selected=True)
    network_tab.cd(node.parent().path())
    network_tab.frameSelection()


def _material_selection_menu():
    """Shows a menu in which the user can pick a material subnet from all material
    libraries to add their textures to.

    Returns:
        Material node
    """
    import hou

    material_library_nodes = hou.nodeType(
        hou.lopNodeTypeCategory(), "materiallibrary"
    ).instances()

    all_material_nodes = []
    for material_library in material_library_nodes:
        for node in material_library.allSubChildren():
            if node.type().name() == "subnet":
                all_material_nodes.append(node)

    if not all_material_nodes:
        hou.ui.displayMessage(
            "You don't have any material subnets in your scene. Please make one to add the image node to.",
            severity=hou.severityType.Error,
        )
        return

    material_node_names = [material_node.name() for material_node in all_material_nodes]

    material_node_choice = hou.ui.selectFromList(
        material_node_names,
        exclusive=True,
        title="Select material node to add image node to.",
    )

    if not material_node_choice:
        return None

    return all_material_nodes[material_node_choice[0]]