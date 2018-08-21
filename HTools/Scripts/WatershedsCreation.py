#-------------------------------------------------------------------------------
# Name:        WatershedsCreation.py
# Purpose:     Same item as PourpointCreation, but with added functionality.
#              This steps through the process actually creating watersheds from the
#              pourpoints.
#
# Author:      aheadman
#
# Created:     11/10/2016
#-------------------------------------------------------------------------------
from __future__ import print_function, absolute_import
import arcpy, os, traceback
from egis import GPMsg, MsgError
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *

def CreateWatersheds(Huc12, FlowAcc, FlowDir, FlowLines, StrBuff, workspace, OutFile, OutRaster, OutSheds):
    try:
        env.workspace = workspace
        env.overwriteOutput = True
        Huc12lyr = arcpy.MakeFeatureLayer_management(Huc12, 'huc12lyr')
        LyrLength = arcpy.GetCount_management(Huc12lyr)
        SaveNum = 1
        OutList = []
        for row in arcpy.da.SearchCursor(Huc12, ['TNMID']):
            GPMsg("Creating pourpoint " + str(SaveNum) + " of " + str(LyrLength.getOutput(0)))
            # Creates ad hoc temp files for each HUC input.
            where = "TNMID" + "='" + row[0] + "'"
            arcpy.SelectLayerByAttribute_management(Huc12lyr, 'NEW_SELECTION', where)
            TempHuc12 = workspace+os.sep+'TempHuc12'
            arcpy.CopyFeatures_management(Huc12lyr, TempHuc12)

            # Clips and buffers flowlines to the HUC12
            arcpy.Clip_analysis(FlowLines, TempHuc12, 'TempClipFL')
            TempClipFL = 'TempClipFL'
            TempBuff = 'TempBufferFL'
            arcpy.Buffer_analysis(TempClipFL, TempBuff, str(StrBuff)+" Meters",  "FULL", "FLAT", "ALL")
            arcpy.Clip_analysis(TempBuff, TempHuc12, 'TempBuff2')
            arcpy.Delete_management(TempBuff)
            TempBuff = 'TempBuff2'
            TempMask = 'TempMask'

            # Extacts the FlowAcc model relevant to the existing flowlines.
            Mask = ExtractByMask(FlowAcc, TempBuff)
            Mask.save(TempMask)

            #Find the maximum value in the flow accumulation raster, uses this as
            #the pourpoint
            Result = arcpy.GetRasterProperties_management(TempMask, "MAXIMUM")
            ResultOut = float(Result.getOutput(0))
            outRast = 'outRast' + str(SaveNum)
            outRas = Con(Raster(TempMask), 1, "", "Value =" +str(Result))
            outRas.save(outRast)
            SaveNum = SaveNum + 1
            OutList.append(outRast)
            TempList = [TempBuff, TempClipFL, TempHuc12, TempMask]
            for Temp in TempList:
                arcpy.Delete_management(Temp)

        # Creats the actual point files (initially these were polygons, hence the naming
        # scheme, it didn't work).
        GPMsg("Saving output...")
        OutPolys=[]
        SaveNum = 1
        for item in OutList:
            OutPoly = 'OutPoly' + str(SaveNum)
            arcpy.RasterToPoint_conversion(item, OutPoly)
            OutPolys.append(OutPoly)
            SaveNum = SaveNum+1
            arcpy.Delete_management(item)

        PourPointPolygons = OutFile
        for poly in OutPolys:
            if arcpy.Exists(PourPointPolygons):
                arcpy.Append_management(poly, PourPointPolygons, "NO_TEST", "", "")
                arcpy.Delete_management(poly)
            else:
                arcpy.CopyFeatures_management(poly, PourPointPolygons)
                arcpy.Delete_management(poly)

        # Adding an attribution step
        GPMsg("Adding Attribution...")
        PourPoints = OutFile
        arcpy.AddField_management(PourPoints, "Huc12", "TEXT", field_length=14)
        PourPointsLyr = arcpy.MakeFeatureLayer_management(PourPoints, 'PourPoints_lyr')
        for point in arcpy.da.SearchCursor(PourPoints, ['OBJECTID']):
            TempPoint = "TempPoint_"+str(point[0])
            where = "OBJECTID" + "=" + str(point[0])
            arcpy.SelectLayerByAttribute_management(PourPointsLyr, 'NEW_SELECTION', where)
            arcpy.CopyFeatures_management(PourPointsLyr, TempPoint)
            arcpy.SelectLayerByLocation_management(Huc12lyr, "contains", TempPoint)
            cursor = arcpy.da.SearchCursor(Huc12lyr, ['HUC12'])
            for row in cursor:
                HucVal = str(row[0])
                with arcpy.da.UpdateCursor(PourPoints, ['OBJECTID', 'Huc12'], where) as update:
                    for value in update:
                        value[1] = HucVal
                        update.updateRow(value)
            arcpy.Delete_management(TempPoint)

        # Runs SnapPoints to build a snap points raster for the Watershed step.
        GPMsg("Snapping pour points...")
        SnapPoints = SnapPourPoint(PourPointPolygons, FlowAcc, "10", 'OBJECTID')
        SnapPoints.save(OutRaster)
        
        # Runs sa.Watershed and RasterToPolygon conversion.
        GPMsg("Building watersheds...")
        outWatershed = Watershed(FlowDir, OutRaster, "VALUE")
        outWatershed.save('ShedRaster')
        arcpy.RasterToPolygon_conversion('ShedRaster', OutSheds, "SIMPLIFY", "VALUE")

        # Adding and filling out HUC12, calculate area and QA/QC fields.
        watersheds = OutSheds
        pourPoints = PourPoints
        arcpy.AddField_management(watersheds, "Huc12", "TEXT", field_length=14)
        arcpy.AddField_management(watersheds, "SqKm", "DOUBLE")
        arcpy.AddField_management(watersheds, "QAComp", "DOUBLE")
        arcpy.AddField_management(watersheds, "QAPriority", "TEXT", field_length=10)
        arcpy.AddField_management(watersheds, "QAReason", "TEXT", field_length=50)
        arcpy.AddField_management(watersheds, "QAComment", "TEXT", field_length=200)

        # populate the Sqkm field
        sqKmExp = "!SHAPE.AREA@SQUAREKILOMETERS!"
        arcpy.CalculateField_management(watersheds, "SqKm", sqKmExp, "PYTHON_9.3")

        # populate the Huc12 field
        ShedsLyr = arcpy.MakeFeatureLayer_management(watersheds, 'Sheds_lyr')
        PointsLyr = arcpy.MakeFeatureLayer_management(pourPoints, 'Points_lyr')
        for shed in arcpy.da.SearchCursor(watersheds, ['OBJECTID']):
              tempPoly = "TempPoly"+str(shed[0])
              where = "OBJECTID" + "=" + str(shed[0])
              arcpy.SelectLayerByAttribute_management(ShedsLyr, 'NEW_SELECTION', where)
              arcpy.CopyFeatures_management(ShedsLyr, tempPoly)
              arcpy.SelectLayerByLocation_management(PointsLyr, "WITHIN", tempPoly)
              cursor = arcpy.da.SearchCursor(PointsLyr, ['Huc12'])
              for row in cursor:
                  HucVal = str(row[0])
                  with arcpy.da.UpdateCursor(watersheds, ['OBJECTID','Huc12'], where) as update:
                      for value in update:
                          value[1] = HucVal
                          update.updateRow(value)
              arcpy.Delete_management(tempPoly)
        
        # Checks in the field for null values, usually caused by slivers created in the
        # rasterToPolygon process. Else statment fills in the QAComp field.
        with arcpy.da.UpdateCursor(watersheds, ['Huc12', 'QAPriority', 'QAReason', 'SqKm', 'QAComp']) as update:
            for row in update:
                if row[0] is None:
                    row[1] = "HIGH"
                    row[2] = "HUC12 code is null"
                    update.updateRow(row)
                else:
                    where = "HUC12" + "='" + row[0] + "'"
                    arcpy.SelectLayerByAttribute_management(Huc12lyr, "NEW_SELECTION", where)
                    cursor = arcpy.da.SearchCursor(Huc12lyr, ['HUC12', 'AreaSqKm'])
                    for cur in cursor:
                        row[4] = row[3]/cur[1]
                        update.updateRow(row)
                if row[4] is not None:
                    if row[4] >= 1.10:
                        row[1] = "HIGH"
                        row[2] = "Area mismatch > 10%"
                        update.updateRow(row)
                    elif row[4] < 1.10 and row[4] > 1.05:
                        row[1] = "check"
                        row[2] = "Area mismatch 5%-10%"
                        update.updateRow(row)
                    elif row[4] <= 0.90:
                        row[1] = "HIGH"
                        row[2] = "Area mismatch > 10%"
                        update.updateRow(row)
                    elif row[4] > 0.90 and row[4] < 0.95:
                        row[1] = "check"
                        row[2] = "Area mismatch 5%-10%"
                        update.updateRow(row)

    except MsgError, xmsg:
        GPMsg("e", str(xmsg))

##Huc12 = r'E:\GIS\ProblemChildren.gdb\Huc12'
##FlowAcc = r'E:\GIS\Matanuska.gdb\FlowAcc2'
##FlowDir = r'E:\GIS\Matanuska.gdb\FlowDir'
##FlowLines = r'E:\GIS\ProblemChildren.gdb\Matanuska_Flowline'
##workspace = r'E:\GIS\Matanuska.gdb'
##OutFile = r'E:\GIS\Matanuska.gdb\PourPoints'
##OutRaster = r'E:\GIS\Matanuska.gdb\Snaps'
##OutSheds = r'E:\GIS\Matanuska.gdb\WaterSheds'
##
##CreateWatersheds(Huc12, FlowAcc, FlowDir, FlowLines, workspace, OutFile, OutRaster, OutSheds)


if __name__ == "__main__":
    # ArcGIS Script tool interface
    argv = tuple(arcpy.GetParameterAsText(i)
        for i in range(arcpy.GetArgumentCount()))
    CreateWatersheds(*argv)
