bl_info = {
    "name": "WBC3 Sprite Tools",
    "author": "xackery + Codex",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > WBC3",
    "description": "Render WBC3-style directional animation spritesheets.",
    "category": "Import-Export",
}

import math
import os
from dataclasses import dataclass

import bpy
from mathutils import Matrix, Vector


CAMERA_NAME = "wbc3-camera"
SUN_NAME = "wbc3-sun"
KEY_LIGHT_NAME = "wbc3-key"
FILL_LIGHT_NAME = "wbc3-fill"
RIM_LIGHT_NAME = "wbc3-rim"

DEFAULT_STATES = ("ambient", "die", "fight", "walk", "stand", "look")
DEFAULT_DIRECTIONS = (
    ("up", 0.0),
    ("up_right", -45.0),
    ("right", -90.0),
    ("down_right", -135.0),
    ("down", -180.0),
    ("down_left", -225.0),
    ("left", -270.0),
    ("up_left", -315.0),
    ("up_close", -360.0),
)


def wbc3_camera_elevation():
    return math.degrees(math.asin(68.0 / 96.0))


def wbc3_sun_bearing(camera_elevation_degrees):
    ce = math.radians(camera_elevation_degrees)
    return math.degrees(math.atan((160.0 / 276.0) / math.sin(ce))) * -1.0


def wbc3_sun_elevation(camera_elevation_degrees, sun_bearing_degrees):
    ce = math.radians(camera_elevation_degrees)
    sb = math.radians(sun_bearing_degrees)
    return math.degrees(math.atan((math.cos(sb) / math.cos(ce)) * (318.0 / 276.0)))


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def direction_vector(bearing_degrees, elevation_degrees, distance):
    bearing = math.radians(bearing_degrees)
    elevation = math.radians(elevation_degrees)
    horizontal = math.cos(elevation) * distance
    return Vector(
        (
            math.sin(bearing) * horizontal,
            -math.cos(bearing) * horizontal,
            math.sin(elevation) * distance,
        )
    )


def get_or_create_camera(context):
    scene = context.scene
    props = scene.wbc3_sprite_props
    camera = bpy.data.objects.get(CAMERA_NAME)
    if camera is None:
        camera_data = bpy.data.cameras.new(CAMERA_NAME)
        camera = bpy.data.objects.new(CAMERA_NAME, camera_data)
        scene.collection.objects.link(camera)

    camera.data.type = "ORTHO"
    camera.data.ortho_scale = props.ortho_scale
    camera.location = direction_vector(
        props.camera_bearing,
        props.camera_elevation,
        props.camera_distance,
    )
    look_at(camera, (0.0, 0.0, props.target_height))
    scene.camera = camera
    return camera


def get_or_create_sun(context):
    scene = context.scene
    props = scene.wbc3_sprite_props
    sun = bpy.data.objects.get(SUN_NAME)
    if sun is None:
        sun_data = bpy.data.lights.new(SUN_NAME, "SUN")
        sun = bpy.data.objects.new(SUN_NAME, sun_data)
        scene.collection.objects.link(sun)

    sun.data.type = "SUN"
    sun.data.energy = props.sun_energy
    sun.location = direction_vector(
        props.sun_bearing,
        props.sun_elevation,
        props.camera_distance * 0.5,
    )
    look_at(sun, (0.0, 0.0, 0.0))
    return sun


def get_or_create_light(context, name, light_type, location, energy, size=None):
    scene = context.scene
    light = bpy.data.objects.get(name)
    if light is None:
        light_data = bpy.data.lights.new(name, light_type)
        light = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light)

    light.data.type = light_type
    light.data.energy = energy
    if size is not None and hasattr(light.data, "size"):
        light.data.size = size
    light.location = Vector(location)
    look_at(light, (0.0, 0.0, 0.75))
    return light


def setup_render_settings(context):
    scene = context.scene
    props = scene.wbc3_sprite_props
    get_or_create_camera(context)

    scene.render.resolution_x = props.render_width
    scene.render.resolution_y = props.render_height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = props.transparent
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.frame_start = 1
    scene.frame_end = props.max_frames

    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except (TypeError, ValueError):
        scene.render.engine = "BLENDER_EEVEE"

    if hasattr(scene, "eevee"):
        scene.eevee.use_gtao = True
        scene.eevee.gtao_distance = 3
        scene.eevee.gtao_factor = 1.5

    try:
        scene.view_settings.view_transform = "Standard"
    except (TypeError, ValueError):
        pass
    try:
        scene.view_settings.look = "Medium High Contrast"
    except (TypeError, ValueError):
        try:
            scene.view_settings.look = "None"
        except (TypeError, ValueError):
            pass
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1


def setup_wbc3_lights(context):
    props = context.scene.wbc3_sprite_props
    sun = get_or_create_sun(context)
    sun.data.energy = props.sun_energy
    get_or_create_light(context, KEY_LIGHT_NAME, "AREA", (-3.5, -4.5, 5.0), 400, 4.0)
    get_or_create_light(context, FILL_LIGHT_NAME, "AREA", (4.0, 3.5, 3.0), 90, 6.0)
    get_or_create_light(context, RIM_LIGHT_NAME, "POINT", (0.0, 4.0, 3.5), 80)


def animation_setup_target(context):
    if context.object and context.object.type in {"MESH", "ARMATURE", "EMPTY"}:
        return context.object
    for obj in context.selected_objects:
        if obj.type in {"MESH", "ARMATURE", "EMPTY"}:
            return obj
    for obj in context.scene.objects:
        if obj.type in {"MESH", "ARMATURE", "EMPTY"} and not obj.hide_render:
            return obj
    return None


def key_object_pose(obj, frame, location, rotation, scale):
    bpy.context.scene.frame_set(frame)
    obj.location = location
    obj.rotation_euler = rotation
    obj.scale = scale
    obj.keyframe_insert(data_path="location", frame=frame)
    obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    obj.keyframe_insert(data_path="scale", frame=frame)


def create_placeholder_action(obj, state_name, frame_count):
    original_location = obj.location.copy()
    original_rotation = obj.rotation_euler.copy()
    original_scale = obj.scale.copy()

    obj.animation_data_create()
    obj.animation_data.action = None

    def loc(x=0.0, y=0.0, z=0.0):
        return original_location + Vector((x, y, z))

    def rot(x=0.0, y=0.0, z=0.0):
        value = original_rotation.copy()
        value.x += math.radians(x)
        value.y += math.radians(y)
        value.z += math.radians(z)
        return value

    middle = max(1, frame_count // 2)
    end = max(1, frame_count)
    poses = {
        "ambient": (
            (1, loc(), rot(), original_scale),
            (middle, loc(z=0.03), rot(z=2), original_scale),
            (end, loc(), rot(), original_scale),
        ),
        "die": (
            (1, loc(), rot(), original_scale),
            (middle, loc(z=-0.05), rot(x=35), original_scale),
            (end, loc(z=-0.25), rot(x=90), original_scale),
        ),
        "fight": (
            (1, loc(), rot(), original_scale),
            (middle, loc(y=-0.12), rot(x=-8), original_scale),
            (end, loc(), rot(), original_scale),
        ),
        "walk": (
            (1, loc(), rot(z=-3), original_scale),
            (middle, loc(z=0.05), rot(z=3), original_scale),
            (end, loc(), rot(z=-3), original_scale),
        ),
        "stand": (
            (1, loc(), rot(), original_scale),
            (end, loc(), rot(), original_scale),
        ),
        "look": (
            (1, loc(), rot(z=-12), original_scale),
            (middle, loc(), rot(z=12), original_scale),
            (end, loc(), rot(), original_scale),
        ),
    }

    for frame, location, rotation, scale in poses[state_name]:
        key_object_pose(obj, frame, location, rotation, scale)

    action = obj.animation_data.action
    if action:
        action.name = f"wbc3_{state_name}"
        action.use_fake_user = True

    obj.location = original_location
    obj.rotation_euler = original_rotation
    obj.scale = original_scale
    return action


def visible_render_roots(scene):
    candidates = []
    for obj in scene.objects:
        if obj.name in {CAMERA_NAME, SUN_NAME}:
            continue
        if obj.type not in {"MESH", "ARMATURE", "EMPTY"}:
            continue
        if obj.hide_render:
            continue
        candidates.append(obj)

    candidate_set = set(candidates)
    roots = []
    for obj in candidates:
        parent = obj.parent
        has_candidate_parent = False
        while parent is not None:
            if parent in candidate_set:
                has_candidate_parent = True
                break
            parent = parent.parent
        if not has_candidate_parent:
            roots.append(obj)
    return roots


def matching_actions(state_name):
    needle = state_name.lower()
    return [action for action in bpy.data.actions if needle in action.name.lower()]


def animation_targets(scene):
    return [obj for obj in scene.objects if obj.type == "ARMATURE" and not obj.hide_render]


def set_action(obj, action):
    obj.animation_data_create()
    obj.animation_data.action = action


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def abs_path(path):
    return bpy.path.abspath(path)


@dataclass
class RenderedFrame:
    state: str
    direction: str
    frame: int
    path: str


def render_png(context, path, frame):
    scene = context.scene
    scene.frame_set(frame)
    scene.render.filepath = path
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    bpy.ops.render.render(write_still=True)


def load_pixels(path):
    image = bpy.data.images.load(path, check_existing=False)
    width, height = image.size
    pixels = list(image.pixels[:])
    bpy.data.images.remove(image)
    return width, height, pixels


def assemble_sheet(frame_paths, output_path, directions, columns, output_format):
    if not frame_paths:
        return None

    first_width, first_height, _ = load_pixels(frame_paths[0][2])
    sheet_width = first_width * columns
    sheet_height = first_height * len(directions)
    sheet_pixels = [0.0] * (sheet_width * sheet_height * 4)

    for direction_index, _direction_name, path in frame_paths:
        column = frame_paths_by_direction_column(frame_paths, direction_index, path)
        source_width, source_height, source_pixels = load_pixels(path)
        if source_width != first_width or source_height != first_height:
            raise RuntimeError("Rendered frames must all have the same dimensions.")

        dest_x = column * first_width
        dest_y = (len(directions) - 1 - direction_index) * first_height
        for y in range(first_height):
            source_start = y * first_width * 4
            source_end = source_start + first_width * 4
            dest_start = ((dest_y + y) * sheet_width + dest_x) * 4
            sheet_pixels[dest_start : dest_start + first_width * 4] = source_pixels[
                source_start:source_end
            ]

    sheet = bpy.data.images.new(
        name=os.path.basename(output_path),
        width=sheet_width,
        height=sheet_height,
        alpha=True,
    )
    sheet.pixels.foreach_set(sheet_pixels)
    try:
        sheet.filepath_raw = output_path
        sheet.file_format = output_format
        sheet.save()
    except Exception:
        fallback_path = os.path.splitext(output_path)[0] + ".png"
        sheet.filepath_raw = fallback_path
        sheet.file_format = "PNG"
        sheet.save()
        output_path = fallback_path
    finally:
        bpy.data.images.remove(sheet)
    return output_path


def frame_paths_by_direction_column(frame_paths, direction_index, path):
    column = 0
    for candidate_direction, _candidate_name, candidate_path in frame_paths:
        if candidate_direction != direction_index:
            continue
        if candidate_path == path:
            return column
        column += 1
    return column


class WBC3SpriteProperties(bpy.types.PropertyGroup):
    output_dir: bpy.props.StringProperty(
        name="Output",
        subtype="DIR_PATH",
        default="//wbc3_renders",
    )
    states: bpy.props.StringProperty(
        name="States",
        default="ambient,die,fight,walk,stand,look",
        description="Comma-separated action name fragments to render",
    )
    frame_step: bpy.props.IntProperty(name="Frame Step", default=1, min=1, max=60)
    max_frames: bpy.props.IntProperty(
        name="Max Frames",
        default=16,
        min=1,
        max=256,
        description="Maximum frames per state and direction",
    )
    render_width: bpy.props.IntProperty(name="Width", default=96, min=8, max=4096)
    render_height: bpy.props.IntProperty(name="Height", default=96, min=8, max=4096)
    transparent: bpy.props.BoolProperty(name="Transparent", default=True)
    camera_bearing: bpy.props.FloatProperty(name="Camera Bearing", default=0.0)
    camera_elevation: bpy.props.FloatProperty(
        name="Camera Elevation",
        default=wbc3_camera_elevation(),
        description="asin(68/96), about 45 degrees from the WBC3 notes",
    )
    camera_distance: bpy.props.FloatProperty(name="Camera Distance", default=12.0, min=0.1)
    target_height: bpy.props.FloatProperty(name="Target Height", default=0.75)
    ortho_scale: bpy.props.FloatProperty(name="Ortho Scale", default=4.0, min=0.01)
    sun_bearing: bpy.props.FloatProperty(
        name="Sun Bearing",
        default=wbc3_sun_bearing(wbc3_camera_elevation()),
        description="atan(160/276/sin(camera elevation)), negated from the WBC3 notes",
    )
    sun_elevation: bpy.props.FloatProperty(
        name="Sun Elevation",
        default=wbc3_sun_elevation(
            wbc3_camera_elevation(),
            wbc3_sun_bearing(wbc3_camera_elevation()),
        ),
        description="atan(cos(sun bearing)/cos(camera elevation)*318/276)",
    )
    sun_energy: bpy.props.FloatProperty(name="Sun Energy", default=2.5, min=0.0)
    sheet_format: bpy.props.EnumProperty(
        name="Sheet Format",
        items=(("PNG", "PNG", ""), ("WEBP", "WebP", "")),
        default="WEBP",
    )


class WBC3_OT_setup_camera(bpy.types.Operator):
    bl_idname = "wbc3.setup_camera"
    bl_label = "Setup Camera"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        get_or_create_camera(context)
        self.report({"INFO"}, "WBC3 camera configured.")
        return {"FINISHED"}


class WBC3_OT_setup_render(bpy.types.Operator):
    bl_idname = "wbc3.setup_render"
    bl_label = "Setup Render"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        setup_render_settings(context)
        self.report({"INFO"}, "WBC3 render settings configured.")
        return {"FINISHED"}


class WBC3_OT_setup_lights(bpy.types.Operator):
    bl_idname = "wbc3.setup_lights"
    bl_label = "Setup Lights"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        setup_wbc3_lights(context)
        self.report({"INFO"}, "WBC3 lights configured.")
        return {"FINISHED"}


class WBC3_OT_setup_anims(bpy.types.Operator):
    bl_idname = "wbc3.setup_anims"
    bl_label = "Setup Anims"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.wbc3_sprite_props
        target = animation_setup_target(context)
        if target is None:
            self.report({"ERROR"}, "Select a mesh, armature, or empty before creating animations.")
            return {"CANCELLED"}

        original_action = target.animation_data.action if target.animation_data else None
        original_frame = context.scene.frame_current
        states = [state.strip() for state in props.states.split(",") if state.strip()]
        created = 0
        try:
            for state in states:
                state_key = state.lower()
                if state_key not in DEFAULT_STATES:
                    continue
                if create_placeholder_action(target, state_key, props.max_frames):
                    created += 1
        finally:
            target.animation_data_create()
            target.animation_data.action = original_action
            context.scene.frame_set(original_frame)
            context.view_layer.update()

        self.report({"INFO"}, f"Created {created} WBC3 placeholder action(s) on {target.name}.")
        return {"FINISHED"}


class WBC3_OT_render_spritesheets(bpy.types.Operator):
    bl_idname = "wbc3.render_spritesheets"
    bl_label = "Export"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        props = scene.wbc3_sprite_props
        setup_render_settings(context)
        setup_wbc3_lights(context)

        output_dir = ensure_dir(abs_path(props.output_dir))
        states = [state.strip() for state in props.states.split(",") if state.strip()]
        roots = visible_render_roots(scene)
        armatures = animation_targets(scene)
        if not roots:
            self.report({"ERROR"}, "No visible renderable mesh, armature, or empty roots found.")
            return {"CANCELLED"}

        original_matrices = {obj: obj.matrix_world.copy() for obj in roots}
        original_actions = {
            obj: obj.animation_data.action if obj.animation_data else None
            for obj in armatures
        }
        original_frame = scene.frame_current
        original_filepath = scene.render.filepath
        original_resolution = (scene.render.resolution_x, scene.render.resolution_y)
        original_film_transparent = scene.render.film_transparent

        scene.render.resolution_x = props.render_width
        scene.render.resolution_y = props.render_height
        scene.render.film_transparent = props.transparent

        completed = []
        try:
            for state in states:
                actions = matching_actions(state)
                if not actions:
                    self.report({"WARNING"}, f"No action matched '{state}', using current animation.")
                    frame_start = scene.frame_start
                    frame_end = scene.frame_end
                    action = None
                else:
                    action = actions[0]
                    frame_start = int(math.floor(action.frame_range[0]))
                    frame_end = int(math.ceil(action.frame_range[1]))

                if action:
                    for armature in armatures:
                        set_action(armature, action)

                frames = list(range(frame_start, frame_end + 1, props.frame_step))[: props.max_frames]
                state_dir = ensure_dir(os.path.join(output_dir, state))
                frame_paths = []

                for direction_index, (direction_name, angle_degrees) in enumerate(DEFAULT_DIRECTIONS):
                    rotation = Matrix.Rotation(math.radians(angle_degrees), 4, "Z")
                    for obj, matrix in original_matrices.items():
                        obj.matrix_world = rotation @ matrix
                    context.view_layer.update()

                    for frame in frames:
                        filename = f"{state}_{direction_index:02d}_{direction_name}_{frame:04d}.png"
                        path = os.path.join(state_dir, filename)
                        render_png(context, path, frame)
                        frame_paths.append((direction_index, direction_name, path))

                extension = ".webp" if props.sheet_format == "WEBP" else ".png"
                sheet_path = os.path.join(output_dir, f"{state}{extension}")
                saved_path = assemble_sheet(
                    frame_paths,
                    sheet_path,
                    DEFAULT_DIRECTIONS,
                    len(frames),
                    props.sheet_format,
                )
                completed.append(saved_path)
        finally:
            for obj, matrix in original_matrices.items():
                obj.matrix_world = matrix
            for obj, action in original_actions.items():
                if obj.animation_data:
                    obj.animation_data.action = action
            scene.frame_set(original_frame)
            scene.render.filepath = original_filepath
            scene.render.resolution_x, scene.render.resolution_y = original_resolution
            scene.render.film_transparent = original_film_transparent
            context.view_layer.update()

        self.report({"INFO"}, f"Rendered {len(completed)} spritesheet(s) to {output_dir}.")
        return {"FINISHED"}


class WBC3_PT_sprite_tools(bpy.types.Panel):
    bl_label = "WBC3"
    bl_idname = "WBC3_PT_sprite_tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "WBC3"

    def draw(self, context):
        layout = self.layout
        props = context.scene.wbc3_sprite_props

        setup_box = layout.box()
        setup_box.operator("wbc3.setup_render", icon="SCENE")
        setup_box.operator("wbc3.setup_lights", icon="LIGHT")
        setup_box.operator("wbc3.setup_anims", icon="ACTION")

        export_row = layout.row()
        export_row.scale_y = 2.0
        export_row.operator("wbc3.render_spritesheets", text="Export", icon="RENDER_ANIMATION")

        camera_box = layout.box()
        camera_box.label(text="Camera")
        camera_box.operator("wbc3.setup_camera", icon="CAMERA_DATA")
        camera_box.prop(props, "camera_elevation")
        camera_box.prop(props, "camera_bearing")
        camera_box.prop(props, "ortho_scale")
        camera_box.prop(props, "target_height")

        light_box = layout.box()
        light_box.label(text="Sun")
        light_box.prop(props, "sun_bearing")
        light_box.prop(props, "sun_elevation")
        light_box.prop(props, "sun_energy")

        render_box = layout.box()
        render_box.label(text="Spritesheets")
        render_box.prop(props, "output_dir")
        render_box.prop(props, "states")
        render_box.prop(props, "render_width")
        render_box.prop(props, "render_height")
        render_box.prop(props, "frame_step")
        render_box.prop(props, "max_frames")
        render_box.prop(props, "sheet_format")
        render_box.prop(props, "transparent")


classes = (
    WBC3SpriteProperties,
    WBC3_OT_setup_camera,
    WBC3_OT_setup_render,
    WBC3_OT_setup_lights,
    WBC3_OT_setup_anims,
    WBC3_OT_render_spritesheets,
    WBC3_PT_sprite_tools,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.wbc3_sprite_props = bpy.props.PointerProperty(type=WBC3SpriteProperties)


def unregister():
    del bpy.types.Scene.wbc3_sprite_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
