#
# Silent Hill 2 PC Map loader
# alanm1
# v0.1 initial release

# Credits:
# SH2 Map file format information from Polymega's https://github.com/Polymega/SilentHillDatabase
# Texture format information from iOrange's SH2tex  https://github.com/iOrange/sh2tex

MeshScale = 1.0         #Override mesh scale (default is 1.0)
debug = 0                       #Prints debug info (1 = on, 0 = off)

from inc_noesis import *
import math
import glob
import re
import copy
from operator import itemgetter, attrgetter
from collections import deque, namedtuple
from io import *
    
def registerNoesisTypes():
    handle = noesis.register("Silent Hill 2: 3D Map [PC]", ".map")
    noesis.setHandlerTypeCheck(handle, meshCheckType)
    noesis.setHandlerLoadModel(handle, meshLoadModel)

    handle = noesis.register("Silent Hill 2: 2D Texture [PC]", ".tex")
    noesis.setHandlerTypeCheck(handle, rawTexCheckType)
    noesis.setHandlerLoadRGBA(handle, rawTexLoad)
 
    #noesis.logPopup()
    return 1
    
def rawTexCheckType(data):
    bs = NoeBitStream(data)
    magic = bs.readUInt()
    if magic == 0x19990901:
        return 1
    else: 
        if debug: print("Unknown file magic: " + str(hex(magic) + " expected 0x19990901!"))
        return 0
    
def rawTexLoad(data, texList):
    bs = NoeBitStream(data)
    texStart = bs.tell()
    bs.seek(texStart + 0x38,NOESEEK_REL)
    ddsWidth = bs.readUShort()
    ddsHeight= bs.readUShort()
    format, isCompressed, unk, ddsSize, ddsSize2 = struct.unpack("BBHII",bs.read(12))
    _,bitw,bith, marker = struct.unpack("IBBH",bs.read(8))   
    bs.seek(texStart+0x50, NOESEEK_ABS)

    if debug: print("rawTexure",ddsWidth,ddsHeight)
    ddsData = bs.readBytes(ddsSize)
    dxt =  noesis.NOESISTEX_DXT3
    if format == 0 :
          dxt =  noesis.NOESISTEX_DXT1
    if format == 1 :
          dxt =  noesis.NOESISTEX_DXT2
    if format == 2 :
          dxt =  noesis.NOESISTEX_DXT3
    if format == 3 :
          dxt =  noesis.NOESISTEX_DXT4
    if format == 4 :
          dxt =  noesis.NOESISTEX_DXT5
    #ddsData = rapi.imageDecodeDXT(ddsData, ddsWidth, ddsHeight,dxt)
    #ddsFmt = noesis.NOESISTEX_RGBA32
    texList.append(NoeTexture("Texture", ddsWidth, ddsHeight, ddsData, dxt))
    return 1


def loadMapSprite(data,texList):
    bs = NoeBitStream(data)
    magic, headerSize, headerAndDataSize,marker = struct.unpack ("IIII",bs.read(16))
    if marker == 0xA7A7A7A7:  #PS2 texture container marker
        bs.read(4 * 12) # unkown
        start_offs = bs.tell()
        # PS2 spriteHerader
        id,x,y,width,height,format, isCompressed, importance ,dataSize, dataSize2,sendpsm,drawpsm,bitshift,tagpoint, bitw, bith, sprite_marker = struct.unpack("IHHHHBBHIIBBBBBBI",bs.read(36)) 
        if  sprite_marker == 0x9999:  # confirm this is PS2 format            
                if format == 8: # palette
                    expectedSize = width* height
                elif format == 4: # PS2 4 bit pallete
                    bitsPerLine = width *4
                    bytesPerLine = (bitsPerLine >> 3) 
                    if (bitsPerLine % 8) != 0:
                        bytesPerLine +=1 
                    expectedSize = bytesPerLine*height
                else: # RGBX8 , RGBA8
                    expectedSize = width * height *4
                pixel_offs = dataSize2 - dataSize
                bs.seek(start_offs + pixel_offs)    
                pixels = bs.read(expectedSize)
                if format == 8 or format == 4 :
                    # read palette header                                    
                    paletteDataSize, _,_,palettesCount, numColors, readSize, unknown[8] = struct.unpack("IIIHBBIIIIIIII",bs.read(20))
                    # TO DO                    

    
def meshCheckType(data):
    bs = NoeBitStream(data)
    ### skip extra header
    uiMagic = bs.readUInt();    
    
    if uiMagic == 0x20010510:
        return 1      
    else:
        if debug: print("Unsupported Mesh header! " + str(uiMagic))
    return 0


class meshFile(object):
    
    def __init__(self, data):
        self.inFile = None
        self.texExtension = ""
                
        self.inFile = NoeBitStream(data)

        self.fileSize = int(len(data))
                        
        self.matList = []
        self.texList = []
        self.texIDs = set()
        self.missingIDs = set()

    @classmethod
    def create_instance(cls, value):
        return cls(value)
    
    def loadMesh(self):                    
        bs = self.inFile
        self.loadMap(bs)

        self.findTexInOtherFile(self.missingIDs)
        return 1

    # not all map file come with the required textures, check other map files in same directory. 
    def findTexInOtherFile(self, missingIDs):
        filepath = rapi.getInputName()
        self.basename  = os.path.splitext(os.path.basename(filepath))[0]
        dir = os.path.dirname(filepath)
        self.area_name = self.basename[:2]  # look for file names with the same first 2 characters

        area_map_wildcard = os.path.join(dir, self.area_name +"*.map")
        all_area_map_files = glob.glob(area_map_wildcard)
        for tex_map_fn in ( all_area_map_files):  # one file at a time
            if tex_map_fn == filepath:  # skip our focus map file
                continue
            if debug: print("Searching texture in file: ",filepath, tex_map_fn)            
            if os.path.exists(tex_map_fn): 
                with open(tex_map_fn,"rb") as file:    
                    data = file.read()
                    magic = struct.unpack("I",data[:4])[0]
                    if magic == 0x20010510: #  PC map file container
                        bs = NoeBitStream(data)
                        # step through all the sub file
                        magic, fileLength, subFileCount,unused = struct.unpack("IIII",bs.read(16))
                        for m in range(subFileCount):                            
                            subFileType, subFileLength, _,_ = struct.unpack("IIII",bs.read(16))
                            if debug: print ("subFile header", subFileType, subFileLength)
                            if subFileType == 1: # ignore geometries
                                bs.seek(subFileLength, NOESEEK_REL)
                            if subFileType == 2: # texture groups
                                magic, _,_, _ = struct.unpack("IIII",bs.read(16))
                                if debug: print ("texture SubFile",magic)
                                textureId = bs.readUInt()
                                while textureId:
                                    width, height, w2,h2, spriteCount, _,_,_,_,_ = struct.unpack("HHHHIHHIII",bs.read(28))
                                    if debug: print ("BCtexture",hex(textureId), width, height, w2,h2, spriteCount)
                                    for i in range(spriteCount):
                                        spriteId, x, y, s_width, s_height, format, pixelDataLength, pixelHeadAndDataLength, _ ,_ \
                                        = struct.unpack("IHHHHIIIII",bs.read(32))
                                        if debug: print ("Texture Header",spriteId, x, y, s_width, s_height, format, pixelDataLength, pixelHeadAndDataLength)
                                        # only the last sprite has texture data
                                        if pixelDataLength > 0:                        
                                            if  textureId in missingIDs:
                                                pixels = bs.read(pixelDataLength)
                                            
                                                bcFormat = noesis.FOURCC_BC2                                            
                                                if format == 0x100:  
                                                        bcFormat = noesis.FOURCC_BC1
                                                if format == 0x102:
                                                        bcFormat = noesis.FOURCC_BC2
                                                if format == 0x103 or format == 0x104:
                                                        bcFormat = noesis.FOURCC_BC3

                                                texName= '{0:#010x}'.format(textureId)      
                                                ddsData = rapi.imageDecodeDXT(pixels, s_width, s_height, bcFormat)
                                                ddsFmt = noesis.NOESISTEX_RGBA32
                                                if debug: print ("++++ Found texture from this file:",texName)
                                                self.texList.append(NoeTexture(texName, s_width, s_height, ddsData, ddsFmt))   
                                                self.texIDs.add(textureId)                      
                                                missingIDs.remove(textureId)
                                                if debug: print ("missing set:",missingIDs)
                                                if len(missingIDs) == 0:  # found all missing texture
                                                    return 1
                                            else:
                                                bs.seek(pixelDataLength, NOESEEK_REL)
                                        else:
                                            pixels = None
                                        
                                    textureId = bs.readUInt()
                                bs.seek(12,1) # skip padding
        return 0

        
    def loadMap(self, bs):    
        magic, fileLength, subFileCount,unused = struct.unpack("IIII",bs.read(16))
        if debug: print ("File header",  magic, fileLength, subFileCount,unused)
        for m in range(subFileCount):
            self.fileBody(bs)
        return 1
    
    def fileBody(self, bs):
        subFileType, subFileLength, _,_ = struct.unpack("IIII",bs.read(16))
        if debug: print ("subFile header", subFileType, subFileLength)
        if subFileType == 1:
            geoStart = bs.tell()
            magic,gemometryCount, geometrySize, meterialCount =  struct.unpack("IIII",bs.read(16))
            if debug: print ("geom subFile",magic,gemometryCount, geometrySize, meterialCount)
            for i in range(gemometryCount):
                pos = bs.tell()                
                geo_id, meshGroupSize,offsetToOpaqueGroup, offsetToTransparentGroup, offsetToDecals = struct.unpack("IIIII",bs.read(20))
                if debug: print ("geom header",geo_id, hex(meshGroupSize),hex(offsetToOpaqueGroup), hex(offsetToTransparentGroup), hex(offsetToDecals))
                if offsetToOpaqueGroup > 0:
                    bs.seek(pos+offsetToOpaqueGroup)
                    self.loadMeshGroup(bs,"opaque")
                if offsetToTransparentGroup > 0:
                    bs.seek(pos+offsetToTransparentGroup)
                    self.loadMeshGroup(bs,"transparent")
                if offsetToDecals > 0:
                    bs.seek(pos+offsetToDecals)
                    self.loadDecals(bs)
                bs.seek(pos + meshGroupSize)
            # material
            bs.seek(geoStart + geometrySize)
            for i in range(meterialCount):
                mode,textureID, materialColor, overlayColor, specularity = struct.unpack("HHIIf",bs.read(16))
                matName = "Mat_" + str(i)                    
                texName = '{0:#010x}'.format(textureID)
                # what to do with textureID 0 ?
                if textureID and textureID  not in self.texIDs:
                    self.missingIDs.add(textureID)
                mat = NoeMaterial(matName,texName)
                mat.setBlendMode(1,6)
                self.matList.append(mat)                    
                
        if subFileType == 2:
            magic, _,_, _ = struct.unpack("IIII",bs.read(16))
            if debug: print ("texture SubFile",magic)
            textureId = bs.readUInt()
            while textureId:
                width, height, w2,h2, spriteCount, _,_,_,_,_ = struct.unpack("HHHHIHHIII",bs.read(28))
                if debug: print ("BCtexture",hex(textureId), width, height, w2,h2, spriteCount)
                for i in range(spriteCount):
                    spriteId, x, y, s_width, s_height, format, pixelDataLength, pixelHeadAndDataLength, _ ,_ \
                    = struct.unpack("IHHHHIIIII",bs.read(32))
                    if debug: print ("Texture Header",spriteId, x, y, s_width, s_height, format, pixelDataLength, pixelHeadAndDataLength)
                    # only the last sprite has texture data
                    if pixelDataLength > 0:                        
                        pixels = bs.read(pixelDataLength)
                        bcFormat = noesis.FOURCC_BC2
                        
                        if format == 0x100:  
                                bcFormat = noesis.FOURCC_BC1
                        if format == 0x102:
                                bcFormat = noesis.FOURCC_BC2
                        if format == 0x103 or format == 0x104:
                                bcFormat = noesis.FOURCC_BC3
                        
                        texName= '{0:#010x}'.format(textureId)      
                        texFound = False
                        for t in self.texList:   # don't create already exist texture
                            if t.name == texName:
                                texFound = True
                                break                            
                        if texFound == False:
                            ddsData = rapi.imageDecodeDXT(pixels, s_width, s_height, bcFormat)
                            ddsFmt = noesis.NOESISTEX_RGBA32
                            if debug: print ("**** Add texture to list:",texName)
                            self.texList.append(NoeTexture(texName, s_width, s_height, ddsData, ddsFmt))   
                            self.texIDs.add(textureId)                      
                    else:
                        pixels = None
                    
                textureId = bs.readUInt()
            bs.seek(12,1)

    def loadMeshGroup(self,bs,prefix):
        meshGroupStart = bs.tell()
        mapMeshCount = bs.readUInt()
        mapMeshOffsets = struct.unpack("I" * mapMeshCount, bs.read(4* mapMeshCount))
        for i in range(mapMeshCount):
            bs.seek(meshGroupStart + mapMeshOffsets[i])
            meshStart = bs.tell()
            BBoxA = struct.unpack("ffff",bs.read(16))
            BBoxB = struct.unpack("ffff",bs.read(16))
            offsetsToVertexSectionHeader, offsetToIndices, indicesLength, unk, meshPartGroupCount = struct.unpack("IIIII", bs.read(20))
            partGroupStart = bs.tell()           

            bs.seek(meshStart + offsetToIndices )    
            iBuf = bs.read(indicesLength)    
            bs.seek(meshStart + offsetsToVertexSectionHeader )
            verticesLength, vertexSectionCount =         struct.unpack("II", bs.read(8))
            vSectionInfo = [] 
            for j in range(vertexSectionCount):
                sectionStart, vertexSize, sectionLength =   struct.unpack("III", bs.read(12))
                vSectionInfo.append((sectionStart, vertexSize, sectionLength))
            vSectionStart = bs.tell()
            sectionVerts=[]
            vBufs =[]
            for j in range(vertexSectionCount):
                bs.seek(vSectionStart + vSectionInfo[j][0])
                vBuf = bs.read(vSectionInfo[j][2])    
                vBufs.append(vBuf) 
            
            # read all parts and strip
            bs.seek(partGroupStart)
            
            ibOffset = 0
            for j in range(meshPartGroupCount):

                materialIndex, sectionId, meshPartCount = struct.unpack("III", bs.read(12))
                if debug: print ("part header ",materialIndex, sectionId, meshPartCount )



                rapi.rpgSetMaterial("Mat_"+str(materialIndex))

                vertexSize = vSectionInfo[sectionId][1]                    

                uvOffset = 0x0C
                rapi.rpgBindPositionBufferOfs(vBufs[sectionId], noesis.RPGEODATA_FLOAT, vertexSize, 0x0)
                if vertexSize >=0x20:
                    uvOffset = 0x18
                    rapi.rpgBindNormalBufferOfs(vBufs[sectionId], noesis.RPGEODATA_FLOAT, vertexSize, 0xC )
                if vertexSize >=0x24:
                    uvOffset = 0x1C                    
                    #rapi.rpgBindColorBufferOfs(vBufs[sectionId], noesis.RPGEODATA_BYTE, vertexSize, 0x18, 4)
                if vertexSize >=0x14:                    
                    rapi.rpgBindUV1BufferOfs(vBufs[sectionId], noesis.RPGEODATA_FLOAT, vertexSize, uvOffset)


                for k in range(meshPartCount):

                    # Build mesh at the part level.
                    offs_str = '{0:#010x}'.format(meshGroupStart)
                    objname = prefix+"_" + offs_str + '_' + str(i) +'_'
                    objname += str(j) + '_'
                    objname += str(k)

                    rapi.rpgSetName( objname )
                    rapi.rpgSetPosScaleBias((MeshScale, MeshScale, MeshScale), (0, 0, 0))
                    
                    if debug: print (objname)

                    # flip mesh along y-axis (vertial direction)
                    rapi.rpgSetTransform(NoeMat43((NoeVec3((-1, 0, 0)), NoeVec3((0, -1, 0)), NoeVec3((0, 0, 1)), NoeVec3((0, 0, 0)))))     


                    stripLength, unknown1, primitiveType, firstVertex, lastVertex = struct.unpack("HBBHH", bs.read(8))

                    if debug: print("strip info",stripLength, unknown1, primitiveType , firstVertex, lastVertex )    
                    # primitiveType :  1  -  triangle strip, 2 - triangle fan,  3 - triangle list                        

                    idxLen  = stripLength * primitiveType
                    if primitiveType == 1:
                        idxLen = stripLength  
                        triType = noesis.RPGEO_TRIANGLE_STRIP
                    if primitiveType == 3:
                        idxLen = stripLength * 3       
                        triType =  noesis.RPGEO_TRIANGLE            
                    byteLength = idxLen * 2
                    idxBuf = iBuf[ibOffset:ibOffset + byteLength  ]             
                    rapi.rpgCommitTriangles(idxBuf, noesis.RPGEODATA_USHORT, idxLen , triType , 0x1)   
                    ibOffset += byteLength
                rapi.rpgClearBufferBinds() 


    def loadDecals(self,bs):
        pos = bs.tell()
        decalCount = bs.readUInt()
        if debug: print ("Decal group cnt", decalCount) 
        decalOffsets = struct.unpack("I" * decalCount,bs.read(4 * decalCount))
        for i in range(decalCount):
            
            bs.seek(pos + decalOffsets[i])
            self.loadDecalGroup(bs, i)            
            
    def loadDecalGroup(self, bs, decal_group_no):
        decalGroups_start = bs.tell()
        bounddingBoxA = struct.unpack("ffff",bs.read(16))
        bounddingBoxB = struct.unpack("ffff",bs.read(16))
        
        offsetToVerexSectionHeader, offsetToIndices, indicesLength, decalCount = struct.unpack("IIII",bs.read(16))
        if debug: print ("decals group",offsetToVerexSectionHeader, offsetToIndices, indicesLength, decalCount )
        decal_start = bs.tell()

        bs.seek(decalGroups_start + offsetToVerexSectionHeader)
        verticesLength,vertexSectionCount = struct.unpack("II",bs.read(8))
        if debug: print ("vertex sections",verticesLength,vertexSectionCount)
        vBufs = [None] * vertexSectionCount
        vSectionInfo = []
        for j in range(vertexSectionCount):            
            sectionStarts, vertexSize, sectionLength = struct.unpack("III",bs.read(12))
            if debug: print ("vertex section ",j ,sectionStarts, vertexSize, sectionLength)
            vSectionInfo.append((sectionStarts, vertexSize, sectionLength))
        vs_start = bs.tell()
        for j in range(vertexSectionCount):    
            bs.seek(vs_start + vSectionInfo[j][0])
            vBuf = bs.read(vSectionInfo[j][2])
            vBufs[j] = vBuf        

        bs.seek(decalGroups_start + offsetToIndices)
        iBuf = bs.read(indicesLength)

        bs.seek(decal_start)
        iStart = 0
        for i in range(decalCount):
            # Decal header
            materialIndex, sectionId, stripLength, stripCount =  struct.unpack("IIII",bs.read(16))
            if debug: print ("sub decal",materialIndex, sectionId, stripLength,stripCount)
            
            rapi.rpgSetMaterial("Mat_"+str(materialIndex))

            vertexSize = vSectionInfo[sectionId][1]                    
            uvOffset = 0x0C
            rapi.rpgBindPositionBufferOfs(vBufs[sectionId], noesis.RPGEODATA_FLOAT, vertexSize, 0x0)
            if vertexSize >=0x20:
                uvOffset = 0x18
                rapi.rpgBindNormalBufferOfs(vBufs[sectionId], noesis.RPGEODATA_FLOAT, vertexSize, 0xC )
            if vertexSize >=0x24:
                uvOffset = 0x1C                    
                rapi.rpgBindColorBufferOfs(vBufs[sectionId], noesis.RPGEODATA_BYTE, vertexSize, 0x18, 4)
            if vertexSize >=0x14:                    
                rapi.rpgBindUV1BufferOfs(vBufs[sectionId], noesis.RPGEODATA_FLOAT, vertexSize, uvOffset)

            # Build mesh at the decal level.
            offs_str = '{0:#010x}'.format(decalGroups_start)
            objname = 'Decal_' + offs_str + '_'
            objname += str(decal_group_no) + '_'
            objname += str(i)
                        
            rapi.rpgSetName( objname )
            rapi.rpgSetPosScaleBias((MeshScale, MeshScale, MeshScale), (0, 0, 0))
            
            if debug: print (objname)

            # flip mesh along y-axis (vertial direction)
            rapi.rpgSetTransform(NoeMat43((NoeVec3((-1, 0, 0)), NoeVec3((0, -1, 0)), NoeVec3((0, 0, 1)), NoeVec3((0, 0, 0)))))                     

            for j in range(stripCount):
                
                if debug: print ("decal strip", iStart, stripLength)
                faceBuff = iBuf[iStart: iStart + stripLength*2 ]
                rapi.rpgCommitTriangles(faceBuff, noesis.RPGEODATA_USHORT, stripLength, noesis.RPGEO_TRIANGLE_STRIP, 0x1)
                iStart += stripLength * 2  # each index take 2 bytes
            rapi.rpgClearBufferBinds() 

def meshLoadModel(data, mdlList):
    ctx = rapi.rpgCreateContext()
    mesh = meshFile(data)
    mesh.loadMesh()
    try:
        mdl = rapi.rpgConstructModel()
    except:
        mdl = NoeModel()
    mdl.setModelMaterials(NoeModelMaterials(mesh.texList, mesh.matList))
    mdlList.append(mdl)

    return 1
        