# SPDX-FileCopyrightText: 2026 GameSome - mabaci

# SPDX-License-Identifier: GPL-3.0-or-later

bl_info = {
    "name": "BatchForge: Mesh Export Tool",
    "author": "GameSome - mabaci",
    "version": (2, 7, 1),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Batch Export",
    "description": "Batch export objects with origin control, transform reset and Unity FBX presets",
    "doc_url": "https://github.com/GameSomeStudio/BatchForge-Blender-Batch-Export-Tool",
    "tracker_url": "https://github.com/GameSomeStudio/BatchForge-Blender-Batch-Export-Tool/issues",
    "category": "Import-Export",
    "support": "COMMUNITY",
}

import bpy
import os
import time
from mathutils import Vector, Matrix, Euler
from bpy.props import (
    StringProperty,
    BoolProperty,
    EnumProperty,
    FloatVectorProperty,
    PointerProperty,
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
)
from bpy_extras.io_utils import ExportHelper


# =========================================================
# UTILITY FUNCTIONS
# ========================================================

def apply_scale_to_mesh(obj):
    """Apply object scale to mesh data. After: scale=(1,1,1)"""
    if obj.type != 'MESH' or not obj.data:
        return
    
    sx, sy, sz = obj.scale
    if abs(sx-1.0) < 1e-6 and abs(sy-1.0) < 1e-6 and abs(sz-1.0) < 1e-6:
        return
    
    mesh = obj.data
    scale_mat = Matrix.Diagonal(obj.scale).to_4x4()
    for v in mesh.vertices:
        v.co = scale_mat @ v.co
    
    obj.scale = Vector((1.0, 1.0, 1.0))
    mesh.update()


def get_world_bbox_corners(obj):
    """Get accurate bounding box corners in world space"""
    if obj.type != 'MESH' or not obj.data:
        return [obj.location.copy()] * 8
    obj.data.update()
    return [obj.matrix_world @ Vector(c) for c in obj.bound_box]


def get_origin_world(obj, origin_type):
    """Calculate origin point in world coordinates"""
    if origin_type == 'WORLD':
        return obj.location.copy()
    
    if origin_type == 'KEEP':
        return obj.location.copy()
    
    corners = get_world_bbox_corners(obj)
    
    if origin_type == 'CENTER':
        return sum(corners, Vector((0,0,0))) / 8
    
    elif origin_type == 'BOTTOM':
        z_min = min(c.z for c in corners)
        cx = (min(c.x for c in corners) + max(c.x for c in corners)) / 2
        cy = (min(c.y for c in corners) + max(c.y for c in corners)) / 2
        return Vector((cx, cy, z_min))
    
    elif origin_type == 'TOP':
        z_max = max(c.z for c in corners)
        cx = (min(c.x for c in corners) + max(c.x for c in corners)) / 2
        cy = (min(c.y for c in corners) + max(c.y for c in corners)) / 2
        return Vector((cx, cy, z_max))
    
    elif origin_type == 'MASS':
        if obj.data and obj.data.vertices:
            verts = [obj.matrix_world @ v.co for v in obj.data.vertices]
            return sum(verts, Vector((0,0,0))) / len(verts)
        return sum(corners, Vector((0,0,0))) / 8


def set_origin_to_zero(obj, origin_type):
    """Move selected origin point to world (0,0,0)"""
    if obj.type != 'MESH' or not obj.data:
        return
    
    mesh = obj.data
    mesh.update()
    
    if origin_type == 'WORLD':
        current_loc = obj.location.copy()
        mesh.transform(obj.matrix_world)
        mesh.transform(Matrix.Translation(-current_loc))
        obj.location = Vector((0.0, 0.0, 0.0))
        obj.rotation_euler = Euler((0.0, 0.0, 0.0), 'XYZ')
        obj.rotation_mode = 'XYZ'
        obj.scale = Vector((1.0, 1.0, 1.0))
        return
    
    origin_world = get_origin_world(obj, origin_type)
    mesh.transform(obj.matrix_world)
    mesh.transform(Matrix.Translation(-origin_world))
    obj.matrix_world = Matrix.Identity(4)
    obj.location = Vector((0.0, 0.0, 0.0))
    obj.rotation_euler = Euler((0.0, 0.0, 0.0), 'XYZ')
    obj.rotation_mode = 'XYZ'
    obj.scale = Vector((1.0, 1.0, 1.0))


def prepare_export_copy(obj, apply_mods=False):
    """Create export-ready copy with scale applied to mesh"""
    if obj.type != 'MESH':
        return None
    
    loc, rot, sca = obj.matrix_world.decompose()
    rot_euler = rot.to_euler('XYZ')
    clean_rot = Euler((
        round(rot_euler.x, 4),
        round(rot_euler.y, 4),
        round(rot_euler.z, 4)
    ), 'XYZ')
    
    obj_copy = obj.copy()
    
    if apply_mods:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_copy = bpy.data.meshes.new_from_object(obj_eval)
    else:
        mesh_copy = obj.data.copy()
    
    obj_copy.data = mesh_copy
    obj_copy.location = loc
    obj_copy.rotation_mode = 'XYZ'
    obj_copy.rotation_euler = clean_rot
    obj_copy.scale = sca
    
    apply_scale_to_mesh(obj_copy)
    obj_copy.scale = Vector((1.0, 1.0, 1.0))
    mesh_copy.update()
    
    if hasattr(obj.data, 'materials'):
        for mat in obj.data.materials:
            if mat is not None:
                existing = [m.name for m in obj_copy.data.materials if m]
                if mat.name not in existing:
                    obj_copy.data.materials.append(mat)
    
    return obj_copy


def join_hierarchy(obj):
    """Join object hierarchy into single mesh"""
    children = list(obj.children_recursive)
    
    if not children:
        return prepare_export_copy(obj)
    
    loc, rot, sca = obj.matrix_world.decompose()
    rot_euler = rot.to_euler('XYZ')
    clean_rot = Euler((
        round(rot_euler.x, 4),
        round(rot_euler.y, 4),
        round(rot_euler.z, 4)
    ), 'XYZ')
    
    orig_sel = bpy.context.selected_objects[:]
    orig_act = bpy.context.active_object
    
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    for child in children:
        child.select_set(True)
    
    bpy.ops.object.duplicate()
    bpy.ops.object.join()
    
    joined = bpy.context.active_object
    joined.location = loc
    joined.rotation_mode = 'XYZ'
    joined.rotation_euler = clean_rot
    joined.scale = sca
    
    apply_scale_to_mesh(joined)
    joined.data.update()
    
    final_mesh = joined.data.copy()
    bpy.data.objects.remove(joined, do_unlink=True)
    
    result = bpy.data.objects.new("__temp_joined__", final_mesh)
    result.location = loc
    result.rotation_mode = 'XYZ'
    result.rotation_euler = clean_rot
    result.scale = Vector((1.0, 1.0, 1.0))
    
    if hasattr(obj.data, 'materials'):
        for mat in obj.data.materials:
            if mat is not None:
                result.data.materials.append(mat)
    
    bpy.ops.object.select_all(action='DESELECT')
    for o in orig_sel:
        if o.name in bpy.context.view_layer.objects:
            o.select_set(True)
    if orig_act and orig_act.name in bpy.context.view_layer.objects:
        bpy.context.view_layer.objects.active = orig_act
    
    return result


def cleanup(obj):
    """Remove temp object"""
    if obj is None:
        return
    try:
        mesh = obj.data if obj.type == 'MESH' else None
        for col in list(obj.users_collection):
            try:
                col.objects.unlink(obj)
            except:
                pass
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh and mesh.users == 0 and mesh.name in bpy.data.meshes:
            bpy.data.meshes.remove(mesh)
    except:
        pass


def export_blend(obj, filepath):
    """Export single object as .blend"""
    orig_scene = bpy.context.window.scene
    temp = None
    try:
        temp = bpy.data.scenes.new("TEMP_EXPORT")
        cpy = obj.copy()
        cpy.data = obj.data.copy()
        temp.collection.objects.link(cpy)
        bpy.context.window.scene = temp
        bpy.ops.wm.save_as_mainfile(filepath=filepath, copy=True)
        return True
    except:
        return False
    finally:
        bpy.context.window.scene = orig_scene
        if temp:
            bpy.data.scenes.remove(temp)


def export_fbx_with_preset(obj, filepath, settings):
    """Export single object as FBX with preset support"""
    bpy.context.scene.collection.objects.link(obj)
    
    try:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        
        # Base FBX settings
        fbx_settings = {
            'filepath': filepath,
            'use_selection': True,
            'object_types': {'MESH'},
            'embed_textures': settings.embed_textures,
            'path_mode': 'COPY' if settings.copy_materials else 'AUTO',
        }
        
        # Apply preset settings
        if settings.fbx_preset == 'UNITY':
            fbx_settings.update({
                'axis_forward': '-Z',
                'axis_up': 'Y',
                'apply_unit_scale': True,
                'apply_scale_options': 'FBX_SCALE_ALL',
                'bake_space_transform': True,
                'use_mesh_modifiers': settings.apply_modifiers,
                'use_custom_props': False,
                'add_leaf_bones': False,
                'primary_bone_axis': 'Y',
                'secondary_bone_axis': 'X',
            })
        elif settings.fbx_preset == 'UNREAL':
            fbx_settings.update({
                'axis_forward': 'X',
                'axis_up': 'Z',
                'apply_unit_scale': True,
                'apply_scale_options': 'FBX_SCALE_ALL',
                'bake_space_transform': True,
                'use_custom_props': False,
            })
        elif settings.fbx_preset == 'CUSTOM':
            fbx_settings.update({
                'axis_forward': settings.fbx_manual_forward,
                'axis_up': settings.fbx_manual_up,
                'apply_unit_scale': True,
                'apply_scale_options': 'FBX_SCALE_ALL',
            })
        else:
            fbx_settings.update({
                'axis_forward': '-Z',
                'axis_up': 'Y',
                'apply_unit_scale': True,
                'apply_scale_options': 'FBX_SCALE_ALL',
            })
        
        bpy.ops.export_scene.fbx(**fbx_settings)
        return True
    except Exception as e:
        print(f"FBX export error: {e}")
        return False
    finally:
        bpy.context.scene.collection.objects.unlink(obj)


def generate_object_report(obj, filepath, format_type, settings):
    """Generate detailed report for exported object"""
    lines = []
    lines.append("=" * 70)
    lines.append(f"OBJECT REPORT: {obj.name}")
    lines.append("=" * 70)
    
    lines.append(f"Export Format: {format_type}")
    lines.append(f"File: {os.path.basename(filepath)}")
    lines.append(f"Path: {os.path.dirname(filepath)}")
    lines.append("")
    
    if obj.type == 'MESH' and obj.data:
        mesh = obj.data
        lines.append("-" * 50)
        lines.append("GEOMETRY")
        lines.append("-" * 50)
        lines.append(f"  Vertices: {len(mesh.vertices):,}")
        lines.append(f"  Edges: {len(mesh.edges):,}")
        lines.append(f"  Faces: {len(mesh.polygons):,}")
        lines.append(f"  Triangles: {sum(len(p.vertices)-2 for p in mesh.polygons):,}")
        ngons = [p for p in mesh.polygons if len(p.vertices) > 4]
        if ngons:
            lines.append(f"  WARNING: {len(ngons)} N-gons detected")
        lines.append("")
    
    lines.append("-" * 50)
    lines.append("TRANSFORM")
    lines.append("-" * 50)
    lines.append(f"  Location: ({obj.location.x:.6f}, {obj.location.y:.6f}, {obj.location.z:.6f})")
    if obj.rotation_mode == 'QUATERNION':
        lines.append(f"  Rotation (Quat): W={obj.rotation_quaternion.w:.6f}")
    else:
        lines.append(f"  Rotation (Euler): ({obj.rotation_euler.x:.6f}, {obj.rotation_euler.y:.6f}, {obj.rotation_euler.z:.6f})")
    lines.append(f"  Scale: ({obj.scale.x:.6f}, {obj.scale.y:.6f}, {obj.scale.z:.6f})")
    lines.append("")
    
    if obj.type == 'MESH':
        dims = obj.dimensions
        lines.append("-" * 50)
        lines.append("DIMENSIONS")
        lines.append("-" * 50)
        lines.append(f"  Width (X):  {dims.x:.4f} m  ({dims.x*100:.2f} cm)")
        lines.append(f"  Depth (Y):  {dims.y:.4f} m  ({dims.y*100:.2f} cm)")
        lines.append(f"  Height (Z): {dims.z:.4f} m  ({dims.z*100:.2f} cm)")
        lines.append("")
    
    origin_names = {
        'CENTER': 'Geometric Center',
        'BOTTOM': 'Bottom Center',
        'TOP': 'Top Center',
        'MASS': 'Center of Mass',
        'KEEP': 'Original Pivot',
        'WORLD': 'World Origin (Direct)'
    }
    lines.append("-" * 50)
    lines.append("ORIGIN SETTINGS")
    lines.append("-" * 50)
    lines.append(f"  Origin Type: {origin_names.get(settings.origin_type, settings.origin_type)}")
    lines.append("")
    
    if hasattr(obj, 'data') and hasattr(obj.data, 'materials') and obj.data.materials:
        lines.append("-" * 50)
        lines.append("MATERIALS")
        lines.append("-" * 50)
        for i, mat in enumerate(obj.data.materials):
            if mat:
                lines.append(f"  Slot {i}: {mat.name}")
        lines.append("")
    
    if obj.type == 'MESH' and obj.data and obj.data.polygons:
        lines.append("-" * 50)
        lines.append("FACE ORIENTATION")
        lines.append("-" * 50)
        try:
            mesh = obj.data
            up_faces = sum(1 for p in mesh.polygons if p.normal.z > 0.001)
            down_faces = sum(1 for p in mesh.polygons if p.normal.z < -0.001)
            total = len(mesh.polygons)
            if up_faces > 0:
                lines.append(f"  Facing Up (Z+): {up_faces:,} ({up_faces/total*100:.1f}%)")
            if down_faces > 0:
                lines.append(f"  Facing Down (Z-): {down_faces:,} ({down_faces/total*100:.1f}%)")
        except:
            lines.append(f"  Total Faces: {len(mesh.polygons):,}")
        lines.append("")
    
    lines.append("-" * 50)
    lines.append("NOTES & TIPS")
    lines.append("-" * 50)
    if obj.type == 'MESH' and obj.data:
        tri_count = sum(len(p.vertices)-2 for p in obj.data.polygons)
        if tri_count > 50000:
            lines.append(f"  Triangle Count: {tri_count:,} (HIGH)")
        elif tri_count > 10000:
            lines.append(f"  Triangle Count: {tri_count:,} (MEDIUM)")
        else:
            lines.append(f"  Triangle Count: {tri_count:,} (LOW)")
    
    if 'Unity' in format_type or 'FBX' in format_type:
        if settings.fbx_preset == 'UNITY':
            lines.append("  Unity Preset: Forward=-Z, Up=Y")
        elif settings.fbx_preset == 'UNREAL':
            lines.append("  Unreal Preset: Forward=X, Up=Z")
    
    lines.append("")
    lines.append("=" * 70)
    lines.append(f"Export completed: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)
    lines.append("Generated by BatchForge: Mesh Export Tool v2.7.1")
    
    return "\n".join(lines)


# ======================================================
# HELP POPUP OPERATOR
# =====================================================

class OBJECT_OT_batch_export_help(Operator):
    """Display help information about Batch Export Tool"""
    bl_idname = "object.batch_export_help"
    bl_label = "How to Use - Batch Export Tool"
    bl_options = {'REGISTER', 'INTERNAL'}
    
    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        box.label(text="Quick Start", icon='PLAY')
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="1. Select source (Selection/All Meshes/Collection)")
        col.label(text="2. Choose origin point placement")
        col.label(text="3. Select export formats and presets")
        col.label(text="4. Click 'Export' button")
        
        box = layout.box()
        box.label(text="Naming Methods", icon='TEXT')
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="• Mesh Name: Uses object's name")
        col.label(text="• Custom Name: Custom name + numbering")
        col.label(text="• Prefix + Mesh: Add prefix (e.g., SM_Cube)")
        col.label(text="• Suffix: Added to end of filename")
        
        box = layout.box()
        box.label(text="Origin Points", icon='PIVOT_CURSOR')
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="• Center: Geometric center → (0,0,0)")
        col.label(text="• Bottom/Top: Align by Z-axis")
        col.label(text="• Center of Mass: Volumetric center")
        col.label(text="• Keep Original: Preserve pivot")
        col.label(text="• World Origin: Move to (0,0,0) directly")
        
        box = layout.box()
        box.label(text="Unity FBX Preset", icon='GAME')
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="• Forward: -Z, Up: Y (Unity standard)")
        col.label(text="• Bake Axis Conversion: Automatic")
        col.label(text="• Apply Scale: All")
        col.label(text="• In Unity: Also check 'Bake Axis Conversion'")
        
        box = layout.box()
        box.label(text="Export Formats", icon='EXPORT')
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="• Blend: Native Blender file")
        col.label(text="• FBX: Unity, Unreal, Maya, 3ds Max")
        col.label(text="• GLB/GLTF: Web, AR, modern engines")
        col.label(text="• OBJ: Universal 3D format")
        col.label(text="• STL: 3D printing")
        col.label(text="• USD/USDC: Universal Scene Description")
    
    def execute(self, context):
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=450)


# ===========================================================
# PROPERTY GROUP
# ============================================================

class BatchExportSettings(PropertyGroup):
    # Source Selection
    source_mode: EnumProperty(
        name="Source",
        description="Which objects to export",
        items=[
            ('SELECTION', 'Selection', 'Export selected objects'),
            ('ALL_MESH', 'All Meshes', 'Export all mesh objects in scene'),
            ('COLLECTION', 'Collection', 'Export from specific collection'),
        ],
        default='SELECTION'
    )
    
    filter_collection: PointerProperty(
        name="Collection",
        type=bpy.types.Collection
    )
    
    # File Naming
    naming_method: EnumProperty(
        name="Naming Method",
        items=[
            ('MESH', 'Mesh Name', 'Use object name'),
            ('CUSTOM', 'Custom Name', 'Custom name + number'),
            ('PREFIX', 'Prefix + Mesh', 'Add prefix'),
        ],
        default='MESH'
    )
    custom_name: StringProperty(name="Custom", default="MyAsset")
    name_prefix: StringProperty(name="Prefix", default="SM_")
    name_suffix: StringProperty(name="Suffix", default="")
    auto_numbering: BoolProperty(name="Auto Numbering", default=True)
    
    # Origin Settings
    origin_type: EnumProperty(
        name="Origin Point",
        items=[
            ('CENTER', 'Center', 'Geometric center → (0,0,0)'),
            ('BOTTOM', 'Bottom Center', 'Bottom → (0,0,0)'),
            ('TOP', 'Top Center', 'Top → (0,0,0)'),
            ('MASS', 'Center of Mass', 'Mass center → (0,0,0)'),
            ('KEEP', 'Keep Original', 'Pivot → (0,0,0)'),
            ('WORLD', 'World Origin', 'Move to (0,0,0) directly'),
        ],
        default='CENTER'
    )
    
    # Transform
    use_current_transform: BoolProperty(name="Use Current Transform", default=False)
    reset_location: BoolProperty(name="Reset Location", default=True)
    reset_rotation: BoolProperty(name="Reset Rotation", default=True)
    reset_scale: BoolProperty(name="Reset Scale", default=True)
    
    custom_location: FloatVectorProperty(name="Location", default=(0.0, 0.0, 0.0), subtype='XYZ', unit='LENGTH')
    custom_rotation: FloatVectorProperty(name="Rotation", default=(0.0, 0.0, 0.0), subtype='EULER', unit='ROTATION')
    custom_scale: FloatVectorProperty(name="Scale", default=(1.0, 1.0, 1.0), subtype='XYZ')
    
    # Export Formats
    export_blend: BoolProperty(name="Blend", default=True)
    export_fbx: BoolProperty(name="FBX", default=True)
    export_glb: BoolProperty(name="GLB", default=False)
    export_gltf: BoolProperty(name="GLTF", default=False)
    export_obj: BoolProperty(name="OBJ", default=False)
    export_stl: BoolProperty(name="STL", default=False)
    export_usd: BoolProperty(name="USD", default=False)
    export_usdc: BoolProperty(name="USDC", default=False)
    
    # FBX Preset
    fbx_preset: EnumProperty(
        name="FBX Preset",
        description="FBX export preset for target application",
        items=[
            ('DEFAULT', 'Default', 'Standard FBX export'),
            ('UNITY', 'Unity Engine', 'Optimized for Unity (Y-up, -Z forward)'),
            ('UNREAL', 'Unreal Engine', 'Optimized for Unreal Engine'),
            ('CUSTOM', 'Custom', 'Manual FBX axis settings'),
        ],
        default='UNITY'
    )
    
    fbx_manual_forward: EnumProperty(
        name="Forward Axis",
        items=[
            ('X', 'X', ''), ('-X', '-X', ''),
            ('Y', 'Y', ''), ('-Y', '-Y', ''),
            ('Z', 'Z', ''), ('-Z', '-Z', ''),
        ],
        default='-Z'
    )
    
    fbx_manual_up: EnumProperty(
        name="Up Axis",
        items=[
            ('X', 'X', ''), ('-X', '-X', ''),
            ('Y', 'Y', ''), ('-Y', '-Y', ''),
            ('Z', 'Z', ''), ('-Z', '-Z', ''),
        ],
        default='Y'
    )
    
    # Export Settings
    export_path: StringProperty(name="Export Path", default="//Exports/", subtype='DIR_PATH')
    create_subfolders: BoolProperty(name="Create Subfolders", default=True)
    apply_modifiers: BoolProperty(name="Apply Modifiers", default=False)
    copy_materials: BoolProperty(name="Copy Materials", default=True)
    embed_textures: BoolProperty(name="Embed Textures", default=False)
    
    # Filtering
    mesh_only: BoolProperty(name="Mesh Only", default=True)
    visible_only: BoolProperty(name="Visible Only", default=False)
    
    # Other
    overwrite_existing: BoolProperty(name="Overwrite Existing", default=False)
    create_log: BoolProperty(name="Create Log", default=True)


# ============================================================
# MAIN OPERATOR
# ============================================================

class OBJECT_OT_batch_export(Operator):
    """Export objects individually with origin, transform, and format settings"""
    bl_idname = "object.batch_export"
    bl_label = "Batch Export"
    bl_options = {'REGISTER', 'UNDO'}
    
    _timer = None
    _objects = []
    _idx = 0
    _failed = []
    _log = []
    
    def get_objects(self, context):
        s = context.scene.batch_export_settings
        
        if s.source_mode == 'SELECTION':
            objs = context.selected_objects
        elif s.source_mode == 'ALL_MESH':
            objs = [o for o in bpy.data.objects if o.type == 'MESH']
        elif s.source_mode == 'COLLECTION':
            if s.filter_collection:
                objs = [o for o in s.filter_collection.all_objects]
            else:
                objs = []
        
        if s.mesh_only:
            objs = [o for o in objs if o.type == 'MESH']
        if s.visible_only:
            objs = [o for o in objs if o.visible_get()]
        
        return objs
    
    def filename(self, s, obj, idx):
        if s.naming_method == 'MESH':
            n = obj.name
        elif s.naming_method == 'CUSTOM':
            n = f"{s.custom_name}_{idx+1}"
        else:
            n = f"{s.name_prefix}{obj.name}"
        if s.name_suffix:
            n += s.name_suffix
        for c in '<>:"/\\|?*\'':
            n = n.replace(c, '_')
        return n
    
    def path(self, s, ext):
        base = bpy.path.abspath(s.export_path)
        if s.create_subfolders:
            m = {'blend':'Blend','fbx':'FBX','glb':'GLTF','gltf':'GLTF',
                 'obj':'OBJ','stl':'STL','usd':'USD','usdc':'USD'}
            base = os.path.join(base, m.get(ext.lstrip('.'), ext.upper()))
        os.makedirs(base, exist_ok=True)
        return base
    
    def unique(self, fp):
        if not os.path.exists(fp):
            return fp
        d, f = os.path.dirname(fp), os.path.basename(fp)
        n, e = os.path.splitext(f)
        c = 1
        while os.path.exists(fp):
            fp = os.path.join(d, f"{n}_{c:03d}{e}")
            c += 1
        return fp
    
    def export_fmt(self, obj, fp, fmt, s):
        bpy.context.scene.collection.objects.link(obj)
        try:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            
            if fmt == 'GLB':
                bpy.ops.export_scene.gltf(filepath=fp, use_selection=True,
                    export_format='GLB', export_image_format='AUTO')
            elif fmt == 'GLTF':
                bpy.ops.export_scene.gltf(filepath=fp, use_selection=True,
                    export_format='GLTF_SEPARATE', export_image_format='AUTO')
            elif fmt == 'OBJ':
                bpy.ops.wm.obj_export(filepath=fp, export_selected_objects=True,
                    export_materials=s.copy_materials)
            elif fmt == 'STL':
                bpy.ops.wm.stl_export(filepath=fp, export_selected_objects=True)
            elif fmt == 'USD':
                bpy.ops.wm.usd_export(filepath=fp, selected_objects_only=True)
            return True
        finally:
            bpy.context.scene.collection.objects.unlink(obj)
    
    def process_one(self, context, obj, idx):
        s = context.scene.batch_export_settings
        fname = self.filename(s, obj, idx)
        tmp = None
        
        try:
            print(f"\n--- {obj.name} ({idx+1}/{len(self._objects)}) ---")
            
            # Create copy
            if len(list(obj.children)) > 0:
                tmp = join_hierarchy(obj)
            else:
                tmp = prepare_export_copy(obj, s.apply_modifiers)
            
            if tmp is None:
                raise Exception("Copy failed")
            
            # Set origin
            if not s.use_current_transform:
                set_origin_to_zero(tmp, s.origin_type)
                print(f"  Origin: {s.origin_type} → (0,0,0)")
            
            # Apply transform
            if s.use_current_transform:
                pass
            else:
                if s.reset_location:
                    tmp.location = Vector(s.custom_location)
                if s.reset_rotation:
                    tmp.rotation_euler = Euler(s.custom_rotation, 'XYZ')
                    tmp.rotation_mode = 'XYZ'
                if s.reset_scale:
                    tmp.scale = Vector(s.custom_scale)
            
            tmp.rotation_mode = 'XYZ'
            
            # Export
            cnt = 0
            
            # Blend
            if s.export_blend:
                try:
                    bp = self.path(s, '.blend')
                    fp = os.path.join(bp, f"{fname}.blend")
                    if not s.overwrite_existing: fp = self.unique(fp)
                    if export_blend(tmp, fp):
                        self._log.append(f"✓ Blend: {fp}")
                        if s.create_log:
                            self._log.append(generate_object_report(tmp, fp, 'Blend', s))
                        cnt += 1
                except Exception as e:
                    self._log.append(f"✗ Blend: {e}")
            
            # FBX with preset
            if s.export_fbx:
                try:
                    p = self.path(s, '.fbx')
                    fp = os.path.join(p, f"{fname}.fbx")
                    if not s.overwrite_existing: fp = self.unique(fp)
                    
                    preset_names = {'UNITY': 'Unity', 'UNREAL': 'Unreal', 'CUSTOM': 'Custom'}
                    preset_label = preset_names.get(s.fbx_preset, '')
                    label = f"FBX ({preset_label})" if preset_label else "FBX"
                    
                    if export_fbx_with_preset(tmp, fp, s):
                        self._log.append(f"✓ {label}: {fp}")
                        if s.create_log:
                            self._log.append(generate_object_report(tmp, fp, label, s))
                        cnt += 1
                except Exception as e:
                    self._log.append(f"✗ FBX: {e}")
            
            # Other formats
            fmts = [('GLB',s.export_glb,'.glb'),('GLTF',s.export_gltf,'.gltf'),
                    ('OBJ',s.export_obj,'.obj'),('STL',s.export_stl,'.stl')]
            
            for fmt, en, ext in fmts:
                if not en: continue
                try:
                    p = self.path(s, ext)
                    fp = os.path.join(p, f"{fname}{ext}")
                    if not s.overwrite_existing: fp = self.unique(fp)
                    if self.export_fmt(tmp, fp, fmt, s):
                        self._log.append(f"✓ {fmt}: {fp}")
                        if s.create_log:
                            self._log.append(generate_object_report(tmp, fp, fmt, s))
                        cnt += 1
                except Exception as e:
                    self._log.append(f"✗ {fmt}: {e}")
            
            # USD
            if s.export_usd or s.export_usdc:
                try:
                    p = self.path(s, '.usd')
                    ext = '.usdc' if s.export_usdc else '.usd'
                    fp = os.path.join(p, f"{fname}{ext}")
                    if not s.overwrite_existing: fp = self.unique(fp)
                    if self.export_fmt(tmp, fp, 'USD', s):
                        self._log.append(f"✓ USD: {fp}")
                        if s.create_log:
                            self._log.append(generate_object_report(tmp, fp, 'USD', s))
                        cnt += 1
                except Exception as e:
                    self._log.append(f"✗ USD: {e}")
            
            if cnt == 0:
                raise Exception("No formats exported")
            
            print(f"  ✓ {cnt} formats")
            return True
            
        except Exception as e:
            self._failed.append((obj.name, str(e)))
            self._log.append(f"✗ {obj.name}: {e}")
            return False
        finally:
            cleanup(tmp)
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            if self._idx < len(self._objects):
                obj = self._objects[self._idx]
                context.window_manager.progress_update(self._idx / len(self._objects))
                self.process_one(context, obj, self._idx)
                self._idx += 1
            else:
                context.window_manager.progress_end()
                if self._timer:
                    context.window_manager.event_timer_remove(self._timer)
                self.report_results(context)
                return {'FINISHED'}
        return {'RUNNING_MODAL'}
    
    def report_results(self, context):
        t = len(self._objects)
        f = len(self._failed)
        s = t - f
        msg = f"Batch Export: {s}/{t} successful"
        print(f"\n{'='*50}\n{msg}\n{'='*50}")
        for m in self._log:
            print(m)
        self.report({'INFO'}, msg)
        if f:
            self.report({'WARNING'}, f"{f} failed")
        if context.scene.batch_export_settings.create_log:
            self.save_log(context)
    
    def save_log(self, context):
        try:
            s = context.scene.batch_export_settings
            p = bpy.path.abspath(s.export_path)
            fp = os.path.join(p, f"batch_export_log_{time.strftime('%Y%m%d_%H%M%S')}.txt")
            with open(fp, 'w', encoding='utf-8') as f:
                f.write("=" * 50 + "\n")
                f.write("BATCH EXPORT LOG\n")
                f.write("=" * 50 + "\n")
                f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total: {len(self._objects)}\n")
                f.write(f"Success: {len(self._objects)-len(self._failed)}\n")
                f.write(f"Failed: {len(self._failed)}\n")
                f.write(f"FBX Preset: {s.fbx_preset}\n")
                f.write("-" * 50 + "\n\n")
                for m in self._log:
                    f.write(m + "\n")
        except Exception as e:
            print(f"Log error: {e}")
    
    def execute(self, context):
        self._objects = self.get_objects(context)
        if not self._objects:
            self.report({'WARNING'}, "No objects found to export!")
            return {'CANCELLED'}
        self._idx = 0
        self._failed = []
        self._log = []
        context.window_manager.progress_begin(0, 1)
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'}, f"Exporting {len(self._objects)} objects...")
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        context.window_manager.progress_end()
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
    
    @staticmethod
    def get_objects_static(context):
        s = context.scene.batch_export_settings
        if s.source_mode == 'SELECTION':
            objs = context.selected_objects
        elif s.source_mode == 'ALL_MESH':
            objs = [o for o in bpy.data.objects if o.type == 'MESH']
        elif s.source_mode == 'COLLECTION':
            if s.filter_collection:
                objs = [o for o in s.filter_collection.all_objects]
            else:
                objs = []
        if s.mesh_only:
            objs = [o for o in objs if o.type == 'MESH']
        if s.visible_only:
            objs = [o for o in objs if o.visible_get()]
        return objs


# ============================================================
# FOLDER SELECTOR
# ============================================================

class OBJECT_OT_select_export_path(Operator, ExportHelper):
    bl_idname = "object.select_export_path"
    bl_label = "Select Export Folder"
    filename_ext = ""
    use_filter_folder = True
    def execute(self, context):
        context.scene.batch_export_settings.export_path = os.path.dirname(self.filepath)
        return {'FINISHED'}


# ============================================================
# UI PANEL
# ============================================================

class VIEW3D_PT_batch_export(Panel):
    bl_label = "Batch Export"
    bl_idname = "VIEW3D_PT_batch_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Batch Export"
    
    def draw(self, context):
        l = self.layout
        s = context.scene.batch_export_settings
        c = l.column(align=True)
        
        # Help button
        c.operator("object.batch_export_help", text="How to Use", icon='HELP')
        
        # Source
        box = c.box()
        box.label(text="Source", icon='OUTLINER_OB_MESH')
        row = box.row(align=True)
        row.prop(s, "source_mode", expand=True)
        if s.source_mode == 'COLLECTION':
            box.prop(s, "filter_collection")
        
        # Naming
        box = c.box()
        box.label(text="Naming", icon='TEXT')
        box.prop(s, "naming_method")
        if s.naming_method == 'CUSTOM':
            box.prop(s, "custom_name")
        elif s.naming_method == 'PREFIX':
            box.prop(s, "name_prefix")
        box.prop(s, "name_suffix")
        box.prop(s, "auto_numbering")
        
        # Origin
        box = c.box()
        box.label(text="Origin Point", icon='PIVOT_CURSOR')
        box.prop(s, "origin_type")
        
        # Transform
        box = c.box()
        box.label(text="Transform", icon='ORIENTATION_GLOBAL')
        col = box.column(align=True)
        row = col.row(align=True); row.prop(s, "reset_location", text="Location")
        if s.reset_location: col.prop(s, "custom_location", text="")
        row = col.row(align=True); row.prop(s, "reset_rotation", text="Rotation")
        if s.reset_rotation: col.prop(s, "custom_rotation", text="")
        row = col.row(align=True); row.prop(s, "reset_scale", text="Scale")
        if s.reset_scale: col.prop(s, "custom_scale", text="")
        box.prop(s, "use_current_transform")
        
        # Export Formats
        box = c.box()
        box.label(text="Export Formats", icon='EXPORT')
        col = box.column(align=True)
        row = col.row(align=True)
        row.prop(s, "export_blend", toggle=True)
        row.prop(s, "export_fbx", toggle=True)
        row = col.row(align=True)
        row.prop(s, "export_glb", toggle=True)
        row.prop(s, "export_gltf", toggle=True)
        row = col.row(align=True)
        row.prop(s, "export_obj", toggle=True)
        row.prop(s, "export_stl", toggle=True)
        row = col.row(align=True)
        row.prop(s, "export_usd", toggle=True)
        row.prop(s, "export_usdc", toggle=True)
        
        # FBX Preset (only when FBX is enabled)
        if s.export_fbx:
            box = c.box()
            box.label(text="FBX Preset", icon='PRESET')
            box.prop(s, "fbx_preset")
            
            if s.fbx_preset == 'UNITY':
                col = box.column(align=True)
                col.label(text="Unity Optimized:", icon='INFO')
                col.label(text="  Forward: -Z, Up: Y")
                col.label(text="  Bake Axis Conversion: Yes")
            elif s.fbx_preset == 'UNREAL':
                col = box.column(align=True)
                col.label(text="Unreal Engine:", icon='INFO')
                col.label(text="  Forward: X, Up: Z")
            elif s.fbx_preset == 'CUSTOM':
                col = box.column(align=True)
                col.prop(s, "fbx_manual_forward")
                col.prop(s, "fbx_manual_up")
        
        # Export Settings
        box = c.box()
        box.label(text="Export Settings", icon='SETTINGS')
        row = box.row(align=True)
        row.prop(s, "export_path", text="")
        row.operator("object.select_export_path", text="", icon='FILE_FOLDER')
        box.prop(s, "create_subfolders")
        box.prop(s, "apply_modifiers")
        box.prop(s, "copy_materials")
        if s.copy_materials:
            box.prop(s, "embed_textures")
        box.prop(s, "overwrite_existing")
        
        # Filter
        box = c.box()
        box.label(text="Filter", icon='FILTER')
        row = box.row(align=True)
        row.prop(s, "mesh_only", toggle=True)
        row.prop(s, "visible_only", toggle=True)
        box.prop(s, "create_log")
        
        # Export Button
        c.separator()
        row = c.row(align=True)
        row.scale_y = 2.0
        
        temp_objs = OBJECT_OT_batch_export.get_objects_static(context)
        n = len(temp_objs)
        t = f"Export ({n} Objects)" if n > 0 else "Export"
        row.operator("object.batch_export", text=t, icon='EXPORT')


# ============================================================
# REGISTER / UNREGISTER
# ============================================================

classes = [
    BatchExportSettings,
    OBJECT_OT_batch_export,
    OBJECT_OT_batch_export_help,
    OBJECT_OT_select_export_path,
    VIEW3D_PT_batch_export,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.batch_export_settings = PointerProperty(type=BatchExportSettings)
    print("Batch Export Tool v2.7 registered successfully")

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.batch_export_settings
    print("Batch Export Tool unregistered")

if __name__ == "__main__":
    register()