# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
    "name" : "bustomize",
    "author" : "sleepybnuuy",
    "description" : "customize+ to blender add-on",
    "blender" : (4, 0, 0),
    "version" : (1, 0, 0),
    "location" : "View3D > Sidebar > bustomize Tab",
    "category" : "Rigging"
}

import bpy
import base64
import json
import zlib
import mathutils
from collections import defaultdict

class BustomizePanel(bpy.types.Panel):
    bl_label = "bustomize"
    bl_idname = "OBJECT_PT_bustomize_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "bustomize"
    bl_options = set()

    def draw(self, context):
        layout = self.layout
        settings = context.scene.bustomize_settings

        row = layout.row()
        row.label(text='Target Armature')
        row = row.row(align=True)
        row.prop(settings, "target_armature", text="")

        row = layout.row()
        row.label(text='Customize+ String')
        row = row.row(align=True)
        row.prop(settings, "cplus_hash", text="", icon="PASTEDOWN")
        row.prop(settings, "flip_axes", text="", icon="CON_ROTLIKE")

        row = layout.row()
        row.operator("object.bustomize", text="do bustomize")
        row = layout.row()
        row.operator("object.bustomize_reset", text="reset armature scale")

class Bustomize(bpy.types.Operator):
    bl_label = "bustomize"
    bl_idname = "object.bustomize"
    bl_description = "apply c+ scale data to targeted armature"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode != 'OBJECT': return False

        settings: Settings = context.scene.bustomize_settings
        if not settings: return False
        if settings.was_applied: return False
        return True

    def execute(self, context: bpy.types.Context):
        settings: Settings = context.scene.bustomize_settings
        if settings.was_applied:
            self.report({'ERROR'}, 'C+ scaling was already applied! Reset then try again')
            return {'CANCELLED'}

        ver, cplus_dict = translate_hash(settings.cplus_hash)
        bonescale_dict = get_bone_scaling(cplus_dict)

        # validate target armature contents
        # only apply scaling to pose bones when we can safely revert
        target_armature = settings.target_armature
        if not target_armature:
            self.report({'ERROR'}, 'Target armature DNE')
            return {'CANCELLED'}
        if not target_armature.type == "ARMATURE":
            self.report({'ERROR'}, 'Did not select a valid armature object')
            return {'CANCELLED'}

        target_bone_names = []
        for bone in target_armature.data.bones:
            if bone.inherit_scale != "FULL":
                self.report({'ERROR'}, f'Armature contains bone {bone.name} which does not inherit parent bone scaling')
                return {'CANCELLED'}
            target_bone_names.append(bone.name)

        # TODO: Armature contains bone j_asi_b_l with unexpected scale: <Vector (1.0000, 1.0000, 1.0000)>
        # for posebone in target_armature.pose.bones:
        #     if posebone.scale != mathutils.Vector((1.0, 1.0, 1.0)):
        #         self.report({'ERROR'}, f'Armature contains bone {posebone.name} with unexpected scale: {posebone.scale}')
        #         return {'CANCELLED'}

        missing_bones = []
        for bonescale_name in bonescale_dict.keys():
            if bonescale_name not in target_bone_names:
                missing_bones.append(bonescale_name)
        if len(missing_bones) == len(bonescale_dict.keys()):
            self.report({'ERROR'}, f'Armature contains no matching bones to scale!')
            return {'CANCELLED'}
        elif len(missing_bones) > 1:
            self.report({'WARNING'}, f'Skipped missing bones: {", ".join(missing_bones)}')
        # end validation

        # unlink parent bone scaling for ALL bones
        for bone in target_armature.data.bones:
            bone.inherit_scale = 'NONE'
        # apply scale to pose bones in bonescale dict
        for posebone in target_armature.pose.bones:
            scale_vector = bonescale_dict[posebone.name]
            if scale_vector:
                if settings.flip_axes:
                    posebone.scale = mathutils.Vector((scale_vector['Z'], scale_vector['X'], scale_vector['Y']))
                else:
                    posebone.scale = mathutils.Vector((scale_vector['X'], scale_vector['Y'], scale_vector['Z']))

        settings.was_applied = True
        return {'FINISHED'}

class BustomizeReset(bpy.types.Operator):
    bl_label = "bustomize"
    bl_idname = "object.bustomize_reset"
    bl_description = "reset scale data"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode != 'OBJECT': return False

        settings: Settings = context.scene.bustomize_settings
        if not settings: return False
        if not settings.was_applied: return False
        return True

    def execute(self, context: bpy.types.Context):
        settings: Settings = context.scene.bustomize_settings
        if not settings.was_applied:
            self.report({'ERROR'}, 'Armature has not been scaled!')
            return {'CANCELLED'}

        # validate target armature
        target_armature = settings.target_armature
        if not target_armature:
            self.report({'ERROR'}, 'Target armature DNE')
            return {'CANCELLED'}
        if not target_armature.type == "ARMATURE":
            self.report({'ERROR'}, 'Did not select a valid armature object')
            return {'CANCELLED'}
        for bone in target_armature.data.bones:
            if bone.inherit_scale != "NONE":
                self.report({'ERROR'}, f'Armature has not been scaled!')
                return {'CANCELLED'}
        # end validation

        # reset scale inheritance and scale factor on all bones
        for bone in target_armature.data.bones:
            bone.inherit_scale = 'FULL'
        for posebone in target_armature.pose.bones:
            posebone.scale = mathutils.Vector((1.0, 1.0, 1.0))

        settings.was_applied = False
        return {'FINISHED'}

class Settings(bpy.types.PropertyGroup):
    target_armature: bpy.props.PointerProperty(name='target armature object', type=bpy.types.Object, poll=lambda self, obj: obj.type == 'ARMATURE') # type: ignore
    cplus_hash: bpy.props.StringProperty(name='clipboard string from c+') # type: ignore
    flip_axes: bpy.props.BoolProperty(default=False, name='flip bone axes (toggle if your scaling applies weird)\ntypically, you should only use this with a problematic devkit skeleton') # type: ignore
    was_applied: bpy.props.BoolProperty(default=False) # type: ignore


def translate_hash(the_hasherrrr: str):
    bytes = base64.b64decode(the_hasherrrr)
    bytes_array = bytearray(bytes)

    # TODO: this is 31 when c+ version should be 4. 'version' key in json is correct
    version = bytes_array[0]

    json_str = zlib.decompress(bytes_array, zlib.MAX_WBITS|16).decode('utf-8')
    json_dict = json.loads(json_str[1:])

    return version, json_dict

def get_bone_scaling(cplus_dict: dict):
    bones = cplus_dict['Bones']
    new_bones = defaultdict(dict)
    for key in bones.keys():
        new_bones[key] = bones[key]['Scaling']
    return new_bones


def register():
    bpy.utils.register_class(Bustomize)
    bpy.utils.register_class(BustomizeReset)
    bpy.utils.register_class(BustomizePanel)
    bpy.utils.register_class(Settings)
    bpy.types.Scene.bustomize_settings = bpy.props.PointerProperty(type=Settings)

def unregister():
    bpy.utils.unregister_class(Bustomize)
    bpy.utils.unregister_class(BustomizeReset)
    bpy.utils.unregister_class(BustomizePanel)
    bpy.utils.unregister_class(Settings)
    del bpy.types.Scene.bustomize_settings

if __name__ == "__main__":
    register()
