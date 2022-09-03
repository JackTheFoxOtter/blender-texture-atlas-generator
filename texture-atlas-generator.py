# ##### BEGIN GPL LICENSE BLOCK #####
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "Texture Atlas Generator",
    "description": "Generate texture atlases (spritesheets) from image sequences.",
    "author": "JackTheFoxOtter",
    "version": (1, 0),
    "blender": (3, 1, 2),
    "location": "Image Editor > Generators > Texture Atlas Generator",
    "warning": "",
    "wiki_url": "https://github.com/JackTheFoxOtter/blender-texture-atlas-generator",
    "tracker_url": "https://github.com/JackTheFoxOtter/blender-texture-atlas-generator/issues",
    "support": "COMMUNITY",
    "category": "Image Editor",
}

"""
Generate texture atlases (spritesheets) from image sequences.
Plugin adds a side panel in the image editor space, which allows navigating to a folder,
choosing a detected image sequence from the folder, choosing a size and order for the atlas and finally
generating a texture atlas from the selected image sequence, storing it as a new image data block.

"""


import bpy

from time import time, sleep
from math import ceil, floor
from os import listdir
from os.path import dirname, isfile, isdir, join
from re import compile, search
from bpy.props import BoolProperty, IntProperty, StringProperty, EnumProperty, CollectionProperty, PointerProperty
from bpy.types import PropertyGroup


# RegEx to find last numerical substring in filename
r_last_numerical = compile('(\d+)\D*$')

# Cache for detected image sequence files (to minimize IO operations)
cached_image_sequences = {}
cached_image_sequences_path = None
cached_image_sequences_dirty = False


def get_image_sequences_in_folder(path):
    """
    Returns image sequences in folder.
    See discover_image_sequences_in_folder(path) for details on evaluation.
    Caches evaluated image sequences for last specified path.
    Re-Evaluates when the path is different to the last cached one or
    global cached_image_sequences_dirty is True.
    
    """
    global cached_image_sequences
    global cached_image_sequences_path
    global cached_image_sequences_dirty
    
    if path != cached_image_sequences_path or cached_image_sequences_dirty:
        cached_image_sequences = discover_image_sequences_in_folder(path)
        cached_image_sequences_path = path
        cached_image_sequences_dirty = False
    
    return cached_image_sequences


def discover_image_sequences_in_folder(path):
    """
    Searches image sequences in folder and returns them.
    Image sequences are detected by determining a mask and frame number for each file.
    The mask is equal to the file name with the last numerical occurence replaced by a '#'.
    The frame number is the number that was replaced from the file name.
    Filenames that evaluated to the same mask are grouped together.
    
    """
    image_sequences = {} # {SCHEMA: [(frameno, file)]]} (Possibly unsorted)
    
    path = path.strip()
    if isdir(path):
        files = [f for f in listdir(path) if isfile(join(path, f))]
        for file in files:
            match = search(r_last_numerical, file)
            schema = file[:match.start(1)] + '#' + file[match.end(1):]
            frame = int(match.group(1))
            
            if schema not in image_sequences.keys():
                image_sequences[schema] = [(frame, file)]
            else:
                image_sequences[schema].append((frame, file))
    
    return image_sequences


class TEXTURE_ATLAS_GENERATOR_Properties(PropertyGroup):
    def use_render_path_update(self, context):
        if self.use_render_path:
            self.path = dirname(context.scene.render.filepath)
    
    use_render_path : BoolProperty(
        name = "Use Render Output Path",
        description = "Use Render Output Path",
        default = True,
        update = use_render_path_update
    )
    
    path : StringProperty(
        name = "",
        description = "Path to Directory",
        maxlen = 1024,
        subtype = 'DIR_PATH'
    )
    
    def sequence_items(self, context):
        items = []
        
        image_sequences = get_image_sequences_in_folder(self.path)
        for schema, images in image_sequences.items():
            items += [(schema, f"{schema} ({len(images)})", f"Sequence with Schema '{schema}' containing {len(images)} Images.")]
        
        if len(items) == 0:
            items += [('none', "", "No Image Sequence found.")]
        
        return items
    
    sequence : EnumProperty(
        name = "",
        description = "Image Sequence",
        items = sequence_items
    )
    
    def image_count_get(self):
        count = 0
        
        image_sequences = get_image_sequences_in_folder(self.path)
        if self.sequence in image_sequences.keys():
            count = len(image_sequences[self.sequence])
        
        return count
    
    image_count : IntProperty(
        name = "Image Count",
        description = "Image Count",
        get = image_count_get
    )
    
    column_count : IntProperty(
        name = "Columns",
        description = "Number of Columns",
        min = 1
    )
    
    def row_count_get(self):
        return ceil(self.image_count / self.column_count)
    
    row_count : IntProperty(
        name = "Rows",
        description = "Number of Rows (automatically determined)",
        get = row_count_get
    )
    
    row_order : EnumProperty(
        name = "Order",
        description = "Order Rows",
        items = [
            ('top_to_bottom', "Top to Bottom", "Order Rows Top to Bottom (First Tile is Top-Left)"),
            ('bottom_to_top', "Bottom to Top", "Order Rows Bottom to Top (First Tile is Bottom-Left)")
        ],
        default = 'top_to_bottom'
    )
    
    output_name : StringProperty(
        name = "",
        description = "Output Name",
        maxlen = 1024,
        default = "Texture Atlas"
    )
    
    overwrite_existing : BoolProperty(
        name = "Overwrite Image if exists",
        description = "Overwrite Output Image if it already exists",
        default = False
    )


class TEXTURE_ATLAS_GENERATOR_PT_generator_panel(bpy.types.Panel):
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Generators"
    bl_label = "Texture Atlas Generator"
    
    def draw(self, context):
        props = context.scene.texture_atlas_generator
        
        # Output path select
        col = self.layout.column(align=True)
        col.prop(props, 'use_render_path')
        row = col.row(align=True)
        col1 = row.column(align=True)
        col1.prop(props, 'path')
        col1.enabled = not props.use_render_path
        row.operator(operator='texture_atlas_generator.mark_image_sequences_cache_dirty', text="", icon='FILE_REFRESH')
        if not isdir(props.path):
            col.label(text="Doesn't exist or no Directory!", icon='ERROR')
        
        self.layout.separator()
        
        # Image Sequence selection
        col = self.layout.column(align=True)
        sequence_count = len([item for item in props.sequence_items(context) if item[0] != 'none'])
        col.label(text=f"Found {sequence_count} Image Sequence{'s' if sequence_count != 1 else ''}")
        row = col.row(align=True)
        row.prop(props, 'sequence')
        row.enabled = sequence_count > 1
        if sequence_count == 0 or props.sequence is None:
            col.label(text="No Image Sequence selected!", icon='ERROR')
        
        self.layout.separator()
        
        # Tiling information
        col = self.layout.column(align=True)
        col.label(text=f"Found {props.image_count} Images in Sequence")
        row = col.row(align=True)
        row.prop(props, 'column_count')
        row = col.row(align=True)
        row.prop(props, 'row_count')
        row.enabled = False # Only display
        if props.image_count > 0:
            unused_tiles = props.column_count * props.row_count - props.image_count
            if unused_tiles > 0:
                self.layout.label(text=f"{unused_tiles} empty Tile{'s' if unused_tiles != 1 else ''}!", icon='INFO')
        col.prop(props, 'row_order')
        
        self.layout.separator()
        
        # File handling
        col = self.layout.column(align=True)
        col.prop(props, 'output_name', text="Name")
        if len(props.output_name) == 0:
            col.label(text="Name can't be empty!", icon='ERROR')
        col.prop(props, 'overwrite_existing')
        
        self.layout.separator()
        
        # Generate Texture Atlas operator
        col = self.layout.column(align=True)
        if props.output_name in bpy.data.images.keys():
            col.label(text="Output Image already exists!", icon='INFO')
        row = col.row(align=True)
        row.operator(operator='texture_atlas_generator.generate_texture_atlas')
        row.enabled = not any([
            sequence_count == 0,
            props.sequence is None,
            len(props.output_name) == 0
        ])
        

class TEXTURE_ATLAS_GENERATOR_OT_mark_image_sequences_cache_dirty(bpy.types.Operator):
    bl_idname = 'texture_atlas_generator.mark_image_sequences_cache_dirty'
    bl_label = ""
    bl_description = "Refresh Image Sequences by marking Image Sequence Cache as dirty"
    
    def execute(self, context):
        global cached_image_sequences_dirty
        cached_image_sequences_dirty = True
        return {'FINISHED'}


class TEXTURE_ATLAS_GENERATOR_OT_generate_texture_atlas(bpy.types.Operator):
    bl_idname = 'texture_atlas_generator.generate_texture_atlas'
    bl_label = "Generate Texture Atlas"
    bl_description = "Generated Texture Atlas based on Generation Settings"
    
    def execute(self, context):
        props = context.scene.texture_atlas_generator
        
        folder_path = props.path
        image_sequences = get_image_sequences_in_folder(folder_path)
        sequence = props.sequence
        files = [file for frame, file in sorted(image_sequences[sequence], key = lambda x: x[1])]
        output_name = props.output_name
        overwrite_existing = props.overwrite_existing
        row_count = props.row_count
        column_count = props.column_count
        row_order = props.row_order
        
        wm = context.window_manager
        wm.progress_begin(0, len(files))
        
        # Load tile images, get max size while doing so
        images = []
        max_size = [0, 0]
        for file in files:
            img = bpy.data.images.load(join(folder_path, file))
            max_size[0] = img.size[0] if img.size[0] > max_size[0] else max_size[0]
            max_size[1] = img.size[1] if img.size[1] > max_size[1] else max_size[1]
            
            images.append(img)

        # Create tilemap image
        tilemap_size = [max_size[0] * column_count, max_size[1] * row_count]
        print(tilemap_size)
        tilemap_img = None
        if overwrite_existing and output_name in bpy.data.images.keys():
            bpy.data.images.remove(bpy.data.images[output_name])
            
        # Blender will automatically add numeric prefix if already exists
        tilemap_img = bpy.data.images.new(output_name, tilemap_size[0], tilemap_size[1])

        # Copy tile pixel data into tilemap image
        tilemap_pixels = [0.0, 0.0, 0.0, 1.0] * tilemap_size[0] * tilemap_size[1]
        for i in range(0, len(files)):
            wm.progress_update(i)
            
            tile_img = images[i]
            tile_size = tile_img.size
            tile_pixels = tile_img.pixels # Sequential list of R G B A components
            
            row_index = row_count - 1 - floor(i / column_count) if row_order == 'top_to_bottom' else floor(i / column_count)
            column_index = i % column_count
            
            for y in range(0, tile_size[1]):
                # Each line of tile image
                tile_offset = y * tile_size[0]
                tile_x1 = tile_offset * 4
                tile_x2 = tile_x1 + tile_size[0] * 4
                
                # Destination line on tilemap image
                tilemap_offset = row_index * tilemap_size[0] * tile_size[1] + column_index * tile_size[0]
                tilemap_x1 = (tilemap_offset + y * tilemap_size[0]) * 4
                tilemap_x2 = tilemap_x1 + tile_size[0] * 4
                
                # Copy tile line to tilemap line
                tilemap_pixels[tilemap_x1:tilemap_x2] = tile_pixels[tile_x1:tile_x2]
                
        tilemap_img.pixels = tilemap_pixels
        
        # Cleanup
        for img in images:
            bpy.data.images.remove(img)
        
        if context.area.type == 'IMAGE_EDITOR':
            # Operator called in image editor, set active image to newly generated one
            context.area.spaces.active.image = tilemap_img
        
        wm.progress_end()
        self.report({'INFO'}, f"Generated \"{tilemap_img.name}\"")
        return {'FINISHED'}


classes = (
    TEXTURE_ATLAS_GENERATOR_Properties,
    TEXTURE_ATLAS_GENERATOR_PT_generator_panel,
    TEXTURE_ATLAS_GENERATOR_OT_mark_image_sequences_cache_dirty,
    TEXTURE_ATLAS_GENERATOR_OT_generate_texture_atlas
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

    bpy.types.Scene.texture_atlas_generator = PointerProperty(type=TEXTURE_ATLAS_GENERATOR_Properties)


def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    
    del bpy.types.Scene.texture_atlas_generator


if __name__ == "__main__":
    register()