# BatchForge: Blender Batch Export Tool
BatchForge is a powerful, all-in-one batch export solution for Blender that streamlines the process of exporting multiple 3D assets with precise control over origin points, transforms, and output formats. Whether you're preparing assets for Unity, Unreal Engine, 3D printing, or archiving your work, BatchForge eliminates repetitive export tasks and ensures consistency across your entire assets.

### ✨ Key Features
🎯 Set Origin Point
Place any point of your mesh exactly at world origin (0,0,0) with six precision modes: Center – Bottom Center – Top Center – Center of Mass – Keep Original – World Origin

This is particularly valuable for game development where consistent pivot points are essential for proper instancing, snapping, and physics interactions.

### 🎮 Game Engine Presets
Export directly with optimized settings for major game engines:

Unity Engine – Automatic axis conversion (Forward: -Z, Up: Y) with baked space transform

Unreal Engine – Correct forward/up axis configuration

Custom – Manual axis control for any engine or DCC application

### 💾 Multi-Format Export
Export each object simultaneously to multiple formats:

Blend – FBX – GLB/GLTF – OBJ – STL – USD/USDC

### 🔄 Transform Control
Reset Location/Rotation/Scale with custom values
Apply Scale – Automatically bakes object scale to mesh data while preserving visual dimensions
Use Current Transform – Keep scene position and rotation for level design workflows

### 📝 Intelligent Naming
Mesh Name – Use object names as filenames
Custom Name – Prefix + Suffix – Auto Numbering – 

### 🔍 Flexible Source Selection
Selection – Export currently selected objects
All Meshes – Export every mesh in the scene
Collection – Export from specific collections for organized workflows

### 📊 Detailed Export Reports
Generate comprehensive log files with:
Geometry statistics (vertices, faces, triangles)
Dimensions and volume information
Face orientation analysis
Material assignments
Export settings summary

### ⚙️ Additional Features
Apply Modifiers – Copy Materials & Embed Textures – Create Subfolders – Progress Bar – Overwrite Protection

### 🚀 How to Use
Select your source – Choose between Selection, All Meshes, or a specific Collection

- Configure naming – Set your preferred naming convention
- Choose origin point – Select where the pivot should be placed
- Set transforms – Optionally reset or customize location, rotation, and scale
- Pick formats – Enable the export formats you need
- Select FBX preset – Choose Unity, Unreal, or Custom axis settings
- Set export path – Choose your output directory
- Click Export – BatchForge processes each object individually

### LOG SAMPLE

BATCH EXPORT LOG
-==================================================
Date: 2026-05-05 18:14:14
Total: 1
Success: 1
Failed: 0
FBX Preset: UNITY
--------------------------------------------------

✓ FBX (Unity): D:\Exports\FBX\barrier02.fbx
-======================================================================
OBJECT REPORT: barrier02.001
-======================================================================
Export Format: FBX (Unity)
File: barrier02.fbx
Path: D:\Exports\FBX

--------------------------------------------------
GEOMETRY
--------------------------------------------------
  Vertices: 492
  Edges: 890
  Faces: 426
  Triangles: 928
  WARNING: 56 N-gons detected

--------------------------------------------------
TRANSFORM
--------------------------------------------------
  Location: (0.000000, 0.000000, 0.000000)
  Rotation (Euler): (0.000000, 0.000000, 0.000000)
  Scale: (1.000000, 1.000000, 1.000000)

--------------------------------------------------
DIMENSIONS
--------------------------------------------------
  Width (X):  0.7003 m  (70.03 cm)
  Depth (Y):  0.1427 m  (14.27 cm)
  Height (Z): 1.1245 m  (112.45 cm)

--------------------------------------------------
ORIGIN SETTINGS
--------------------------------------------------
  Origin Type: Geometric Center

--------------------------------------------------
MATERIALS
--------------------------------------------------
  Slot 0: All_Material

--------------------------------------------------
FACE ORIENTATION
--------------------------------------------------
  Facing Up (Z+): 181 (42.5%)
  Facing Down (Z-): 181 (42.5%)

--------------------------------------------------
NOTES & TIPS
--------------------------------------------------
  Triangle Count: 928 (LOW)
  Unity Preset: Forward=-Z, Up=Y

-======================================================================
Export completed: 2026-05-05 18:14:14
-======================================================================

