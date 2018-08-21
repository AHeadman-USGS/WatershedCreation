from __future__ import print_function, absolute_import
import arcpy, os, traceback
from egis import GPMsg, MsgError
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *

def WatershedPreprocessing (workspace, Elevation, FillOut, FlowAccOut, FlowDirOut):
    try:
        env.workspace = workspace
        GPMsg("Filling...")
        outFill = Fill(Elevation)
        outFill.save(FillOut)
        FlowInput = FillOut
        GPMsg("Flow Direction processing...")
        outFlowDirection = FlowDirection(FlowInput, "FORCE")
        outFlowDirection.save(FlowDirOut)
        FlowDir = FlowDirOut
        GPMsg("Flow Accumulation processing...")
        outFlowAcc = FlowAccumulation(FlowDir)
        outFlowAcc.save(FlowAccOut)

    except MsgError, xmsg:
        GPMsg("e", str(xmsg))

if __name__ == "__main__":
    # ArcGIS Script tool interface
    argv = tuple(arcpy.GetParameterAsText(i)
        for i in range(arcpy.GetArgumentCount()))
    WatershedPreprocessing(*argv)

        
        
        
        
    
