from __future__ import print_function, absolute_import
import arcpy, os, traceback
from egis import GPMsg, MsgError
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *

def watershedRerun(pourPoints, Huc12, FlowDir, FlowAcc, OutSheds, workspace):
    try:
        env.workspace = workspace
        env.overwriteOutput = True
        Huc12lyr = arcpy.MakeFeatureLayer_management(Huc12, 'huc12lyr')
        LyrLength = arcpy.GetCount_management(Huc12lyr)
        SaveNum = 1
        OutList = []

        # Runs SnapPoints to build a snap points raster for the Watershed step.
        OutRaster = 'snap'
        GPMsg("Snapping pour points...")
        SnapPoints = SnapPourPoint(pourPoints, FlowAcc, "5", 'OBJECTID')
        SnapPoints.save(OutRaster)
    
        # Runs sa.Watershed and RasterToPolygon conversion.
        GPMsg("Building watersheds...")
        outWatershed = Watershed(FlowDir, OutRaster, "VALUE")
        outWatershed.save('ShedRaster')
        arcpy.RasterToPolygon_conversion('ShedRaster', OutSheds, "SIMPLIFY", "VALUE")

        watersheds = OutSheds
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

if __name__ == "__main__":
    # ArcGIS Script tool interface
    argv = tuple(arcpy.GetParameterAsText(i)
        for i in range(arcpy.GetArgumentCount()))
    watershedRerun(*argv)
