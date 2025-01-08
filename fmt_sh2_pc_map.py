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
        print("Unknown file magic: " + str(hex(magic) + " expected 0x19990901!"))
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
    if debug:
        print("rawTexure",ddsWidth,ddsHeight)
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

def meshCheckType(data):
    bs = NoeBitStream(data)
    ### skip extra header
    uiMagic = bs.readUInt();    
    
    if uiMagic == 0x20010510:
        return 1      
    else:
        print("Unsupported Mesh header! " + str(uiMagic))
    return 0


class meshFile(object):
    
    def __init__(self, data):
        self.inFile = None
        self.texExtension = ""
                
        self.inFile = NoeBitStream(data)

        self.fileSize = int(len(data))
                        
        self.matList = []
        self.texList = []

    @classmethod
    def create_instance(cls, value):
        return cls(value)
    
    def loadMesh(self):
        filepath = rapi.getInputName()
        self.basename  = os.path.splitext(os.path.basename(filepath))[0]
        # load common textures from area map file , ??.map
        if len(self.basename) > 2:
            dir = os.path.dirname(filepath)
            self.area_name = self.basename[:2]
            
            area_map_fn = os.path.join(dir, self.area_name +".map")
            print("file name ",filepath, area_map_fn)
            # load common map file if it exist in same directory
            if os.path.exists(area_map_fn): 
                with open(area_map_fn,"rb") as file:    
                    tlen = len(self.texList)
                    area_mesh = self.create_instance(file.read())
                    area_mesh.loadMap(area_mesh.inFile)
                    self.texList.extend(area_mesh.texList)
        
        bs = self.inFile
        self.loadMap(bs)
        return 1

    def loadMap(self,bs):    
        magic, fileLength, subFileCount,unused = struct.unpack("IIII",bs.read(16))
        print ("File header",  magic, fileLength, subFileCount,unused)
        for m in range(subFileCount):
            self.fileBody(bs)
        return 1
    
    def fileBody(self, bs):
        subFileType, subFileLength, _,_ = struct.unpack("IIII",bs.read(16))
        print ("subFile header", subFileType, subFileLength)
        if subFileType == 1 :
            geoStart = bs.tell()
            magic,gemometryCount, geometrySize, meterialCount =  struct.unpack("IIII",bs.read(16))
            print ("geom subFile",magic,gemometryCount, geometrySize, meterialCount)
            for i in range(gemometryCount):
                pos = bs.tell()                
                geo_id, meshGroupSize,offsetToOpaqueGroup, offsetToTransparentGroup, offsetToDecals = struct.unpack("IIIII",bs.read(20))
                print ("geom header",geo_id, hex(meshGroupSize),hex(offsetToOpaqueGroup), hex(offsetToTransparentGroup), hex(offsetToDecals))
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
                mat = NoeMaterial(matName,texName)
                mat.setBlendMode(1,6)
                self.matList.append(mat)
                
        if subFileType == 2:
            magic, _,_, _ = struct.unpack("IIII",bs.read(16))
            print ("texture SubFile",magic)
            textureId = bs.readUInt()
            while textureId:
                width, height, w2,h2, spriteCount, _,_,_,_,_ = struct.unpack("HHHHIHHIII",bs.read(28))
                print ("BCtexture",hex(textureId), width, height, w2,h2, spriteCount)
                for i in range(spriteCount):
                    spriteId, x, y, s_width, s_height, format, pixelDataLength, pixelHeadAndDataLength, _ ,_ \
                    = struct.unpack("IHHHHIIIII",bs.read(32))
                    print ("Texture Header",spriteId, x, y, s_width, s_height, format, pixelDataLength, pixelHeadAndDataLength)
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
                        ddsData = rapi.imageDecodeDXT(pixels, s_width, s_height, bcFormat)
                        ddsFmt = noesis.NOESISTEX_RGBA32
                        self.texList.append(NoeTexture(texName, s_width, s_height, ddsData, ddsFmt))                         
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
                print ("part header ",materialIndex, sectionId, meshPartCount )



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
                    
                    print (objname)

                    # flip mesh along y-axis (vertial direction)
                    rapi.rpgSetTransform(NoeMat43((NoeVec3((-1, 0, 0)), NoeVec3((0, -1, 0)), NoeVec3((0, 0, 1)), NoeVec3((0, 0, 0)))))     


                    stripLength, unknown1, primitiveType, firstVertex, lastVertex = struct.unpack("HBBHH", bs.read(8))

                    print("strip info",stripLength, unknown1, primitiveType , firstVertex, lastVertex )    
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
        print ("Decal group cnt", decalCount) 
        decalOffsets = struct.unpack("I" * decalCount,bs.read(4 * decalCount))
        for i in range(decalCount):
            
            bs.seek(pos + decalOffsets[i])
            self.loadDecalGroup(bs, i)            
            
    def loadDecalGroup(self, bs, decal_group_no):
        decalGroups_start = bs.tell()
        bounddingBoxA = struct.unpack("ffff",bs.read(16))
        bounddingBoxB = struct.unpack("ffff",bs.read(16))
        
        offsetToVerexSectionHeader, offsetToIndices, indicesLength, decalCount = struct.unpack("IIII",bs.read(16))
        print ("decals group",offsetToVerexSectionHeader, offsetToIndices, indicesLength, decalCount )
        decal_start = bs.tell()

        bs.seek(decalGroups_start + offsetToVerexSectionHeader)
        verticesLength,vertexSectionCount = struct.unpack("II",bs.read(8))
        print ("vertex sections",verticesLength,vertexSectionCount)
        vBufs = [None] * vertexSectionCount
        vSectionInfo = []
        for j in range(vertexSectionCount):            
            sectionStarts, vertexSize, sectionLength = struct.unpack("III",bs.read(12))
            print ("vertex section ",j ,sectionStarts, vertexSize, sectionLength)
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
            print ("sub decal",materialIndex, sectionId, stripLength,stripCount)
            
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
            offs_str = '{0:#010x}'.format(decal_start)
            objname = 'Decal_'
            objname += str(decal_group_no) + '_'
            objname += str(i)
                        
            rapi.rpgSetName( objname )
            rapi.rpgSetPosScaleBias((MeshScale, MeshScale, MeshScale), (0, 0, 0))
            
            print (objname)

            # flip mesh along y-axis (vertial direction)
            rapi.rpgSetTransform(NoeMat43((NoeVec3((-1, 0, 0)), NoeVec3((0, -1, 0)), NoeVec3((0, 0, 1)), NoeVec3((0, 0, 0)))))                     
            #rapi.rpgBindNormalBufferOfs(normBuff, noesis.RPGEODATA_FLOAT, 0xC, 0x0)

            for j in range(stripCount):
                
                print ("decal strip", iStart, stripLength)
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
        