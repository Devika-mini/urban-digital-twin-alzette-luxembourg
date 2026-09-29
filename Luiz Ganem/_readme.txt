QUASO! 
    |\__/,|   (`\
  _.|o o  |_   ) )
-(((---(((--------

THIS README IS SPECIFIC FOR THE COLLABORATION IN WORKSHOP III. IT AND THE CODE FOLLOWING WILL BE DIFFERENT FROM THE ORIGINAL VERSION FOR MY OWN MAKING.
This is a readme with regards to the building of a digital twin in luxembourg, specifically as of now a 2km long range of the Alzette.
Here I will give a brief overview of the files, scripts, and outputs I made. 
I did use ML for helping me build for the sake of saving time, since searching dictionaries and implementing already exisiting functions is mostly a very straightforward process that can be done well by them with just a few checks. Obviously, I do understand fully this code and did work on it myself just as much.
This readme tho, its all me XD and mostly just a way for me to keep track of my progress as well so it will not be professional at all.
I recommend reading the linked pdf by the lux government explaining the syntax used in their DB.

 /\_/\
( o.o )
 > ^ <

ManifestTiles: Will write a manifest (json report) on a raster jpkg given certain inputs such as area to be manifested. Mostly just for processing luxembourg lidar jpkg and preparing ground for the next script.

MakeDem: Will make a DEM and a WaterMask raster map out of zipped lidar files in the specified DIRs and manifest. Both maps do use the luxembourgish CRS.
    DEM is still generated with the max height in each cell, may be vulnerable to outliers, eventhough it is filled in the following script.

TerrainAnalysis: will make various other derivative maps from the DEM and Watermask. 







ClearWorkspace: The name already says it all -_-     Clears all dirs and files created by other scripts, resetting the dir.

requirements: requirement libs used.























Links used:

    https://data.public.lu/fr/datasets/lidar-2024-releve-3d-du-territoire-luxembourgeois





Heres a copy of my .gitignore if you want to run it all yourself:

    # Python
    __pycache__/
    *.py[cod]

    # Virtual environment
    .venv/
    venv/

    # Data files and dirs
    lidar_manifest.json
    *.pdf
    *.gpkg
    *.qgz
    *.tif
    *.tiff
    *.tif.aux.xml
    terrain_outputs/
    lidar_downloads/
    lidar_tiles/
    *.laz
    *.las
    *.zip

    # IDE / OS
    .vscode/
    .idea/
    .DS_Store
    Thumbs.db


That was it, thank you for your attention. 
Kindest Regards, 
Luiz Ganem




                      /^--^\     /^--^\     /^--^\
                      \____/     \____/     \____/
                     /      \   /      \   /      \
KAT                 |        | |        | |        |
                     \__  __/   \__  __/   \__  __/
|^|^|^|^|^|^|^|^|^|^|^|^\ \^|^|^|^/ /^|^|^|^|^\ \^|^|^|^|^|^|^|^|^|^|^|^|
| | | | | | | | | | | | |\ \| | |/ /| | | | | | \ \ | | | | | | | | | | |
########################/ /######\ \###########/ /#######################
| | | | | | | | | | | | \/| | | | \/| | | | | |\/ | | | | | | | | | | | |
|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|_|

PS: Quaso! Peace out.