import os
import tank
# from os import listdir
# from os.path import isfile, join
# import random
# import sgtk

class BeforeAppLaunch(tank.Hook):

    def execute(self, app_path, app_args, version, engine_name, **kwargs):

        if engine_name == "tk-houdini":          
            os.environ["HOUDINI_DISABLE_CONSOLE"] = "1"
            os.environ["HOUDINI_ANONYMOUS_STATISTICS"] = "0"
            os.environ["HOUDINI_NO_START_PAGE_SPLASH"] = "1"
            os.environ["HOUDINI_SPLASH_MESSAGE"] = "Houdini Seemann (AT)"
            # os.environ["HOUDINI_SPLASH_FILE"] = "R:/00_pipeline/splashscreen/giphy.gif"

            # Random Splashscreen from splashscreen folder
            # tk = sgtk.platform.current_engine().sgtk
            # name = sgtk.util.get_current_user(tk)["name"]
            # if name == "Simon Weck" or name == "Levin Wunder":
            #     path = "R:/00_pipeline/splashscreen"
            #     images = []
            #     for file in listdir(path):
            #         if isfile(join(path, file)) and file.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
            #             images.append(file)
            #     os.environ["HOUDINI_SPLASH_FILE"] = "R:/00_pipeline/splashscreen/" + random.choice(images)

        # if engine_name == "tk-nuke":
        #     tank.util.append_path_to_env_var("NUKE_PATH", "R:/00_pipeline/shotgrid/config/hooks/nuke")
        #     tank.util.append_path_to_env_var("NUKE_PATH", "R:/00_pipeline/.nuke")

        # if engine_name == "tk-blender":
        #     os.environ["SGTK_COMPATIBILITY_DIALOG_SHOWN"] = "1" #Fix Blender Errror when launching from Shotgun
        #     os.environ["PYSIDE2_PYTHONPATH"] = "C:/Users/Simon Weck/Desktop/test"