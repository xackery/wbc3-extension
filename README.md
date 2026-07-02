# wbc3-extension
Blender extension for WBC3

## WBC3 Sprite Tools

This repository contains a Blender add-on package at `wbc3_sprite_tools`.

### Install

1. Run `mage build` to create `bin/wbc3_sprite_tools.zip`.
2. In Blender, open `Edit > Preferences > Add-ons`.
3. Install `bin/wbc3_sprite_tools.zip`.
4. Press `N` in the 3D viewport and open the `WBC3` tab.

During development, run `mage watch` to rebuild `bin/wbc3_sprite_tools.zip`
whenever a watched `.py` file changes. Stop it with `Ctrl+C`.

For Pylance support in VS Code, run `mage pylance`. This creates `.venv`,
installs Blender Python API stubs from `requirements-dev.txt`, and lets Pylance
resolve imports such as `bpy` and `mathutils`.

### What It Does

- Adds or updates a camera named `wbc3-camera`.
- `Setup Render` configures camera, transparent PNG output, resolution, frame range,
  color management, and Eevee ambient occlusion when available.
- `Setup Lights` adds or updates WBC3-prefixed scene lights:
  `wbc3-sun`, `wbc3-key`, `wbc3-fill`, and `wbc3-rim`.
- `Setup Anims` creates placeholder animation actions on the selected object, or the
  first renderable object, for the expected export states.
- Uses the camera and sun math from the WBC3 reference notes:
  - camera elevation: `asin(68/96)`, about 45 degrees
  - sun bearing: `atan(160/276/sin(camera elevation))`, negated
  - sun elevation: `atan(cos(sun bearing)/cos(camera elevation)*318/276)`
- Looks for animation actions whose names contain:
  `ambient`, `die`, `fight`, `walk`, `stand`, or `look`.
- Temporarily rotates visible renderable scene roots through 9 directions:
  up, up right, right, down right, down, down left, left, up left, and up close.
- Renders PNG frame sequences per animation state.
- Combines the rendered PNG frames into one spritesheet per state.

By default, output goes to `//wbc3_renders` beside the active `.blend` file. WebP sheet output is attempted first; if the active Blender build cannot save WebP images, the add-on writes PNG sheets instead.
