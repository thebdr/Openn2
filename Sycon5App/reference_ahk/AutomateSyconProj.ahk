; Ctrl(^) Alt(!) Shift(+) Win(#)

#Requires AutoHotkey v2.0
#SingleInstance Force
#Include %A_ScriptDir%\_lib.ahk

+Esc::ExitApp ;kill switch Shift+Esc

global paramsFolder := A_ScriptDir '\AutomateSyconProj_Data\Parameters'
global csvNodesList := paramsFolder '\NodesList.csv'
global csvQuantities := paramsFolder '\Quantities.csv'
global csvSyconBaseDevices := paramsFolder '\_SyconBaseDevices.csv'


global DevicesList := Devices()

global mouseRowYOffsetPixels := 20
global mousePixelsMovedX:=0, mousePixelsMovedY:=0

^<::
{
    global mouseStartX := 0, mouseStartY := 0
    MouseGetPos(&mouseStartX, &mouseStartY)

    if(!ReadCsv())
    {
        return
    }

    if(!FindAllDevicesInSycon())
    {
        return
    }
    
    Sleep(SetWaitTime(5))
        
    CreateDevicesInSycon()


    OutputDebug 'a'


}

ReadCsv()
{
    result := {NumSyconRows:false, AtLeastOneDeviceType:false, AtLeastOneNode:false}

    ;Quantities.csv
    sArCsvRows := StrSplit(FileRead(csvQuantities), '`n')
    Loop(sArCsvRows.Length)
    {
        sRow := sArCsvRows[A_Index]

        ;skip row
        if(SubStr(sRow,1,1)='#' or SubStr(sRow,1,1)='')
        {
            continue
        }
           
        ;split by ','
        sArSplitRow := StrSplit(sRow, ',')        

        ;special params
        if (SubStr(sRow,1,1)='>')
        {
            switch(sArSplitRow[2])
            {
                case "SyconRows":
                {
                    DevicesList.syconRows := Integer(sArSplitRow[3])

                    result.NumSyconRows := true
                }      
            }
        }
        ;device
        else if(SubStr(sRow,1,1)='@')
        {
            DevicesList.AddType(StrSplit(sArSplitRow[2], '#')[1], StrSplit(sArSplitRow[2], '#')[2], sArSplitRow[3])

            result.AtLeastOneDeviceType := true
        }       
    }

    
    ;NodesList.csv
    sArCsvRows := StrSplit(FileRead(csvNodesList), '`n')
    Loop(sArCsvRows.Length)
    {
        sRow := sArCsvRows[A_Index]

        ;skip row
        if(SubStr(sRow,1,1)='#' or SubStr(sRow,1,1)='')
        {
            continue
        }
           
        ;split by ','
        sArSplitRow := StrSplit(sRow, ',')        

        ;device
        if(SubStr(sRow,1,1)='@')
        {
            DevicesList.AddNode(sArSplitRow[3], sArSplitRow[4], sArSplitRow[5], sArSplitRow[6])

            result.AtLeastOneNode := true
        }       
    }

    return (result.NumSyconRows and result.AtLeastOneDeviceType and result.AtLeastOneNode)
}

FindAllDevicesInSycon()
{   
    ;read base devices from sycon project
    if(!FileExist(csvSyconBaseDevices))
    {
        Loop(DevicesList.syconRows)
        {
            FileAppend(A_Index ',' MouseMvDn_ShiftF10_Down_Enter_ReadText(mouseRowYOffsetPixels) '`n', csvSyconBaseDevices)

            Send '{Enter}'
            Sleep(SetWaitTime(5))
        }    
    }

    ;read csv
    sArCsvRows := StrSplit(FileRead(csvSyconBaseDevices), '`n')

    ;search the base device in sycon
    for(csvLine in sArCsvRows)
    {
        if(csvLine='') 
        {
            continue
        }

        splitCsvLine := StrSplit(csvLine, ',')

        nodeRow := splitCsvLine[1]
        nodeSymbolicName := splitCsvLine[2]

        for(dev in DevicesList.typesList)
        {
            matchFound := SubStr(nodeSymbolicName, 1, StrLen(dev.vendor) + 1 + StrLen(dev.model)) = dev.vendor '#' dev.model

            if(matchFound)
            {
                dev.rowInSycon := Number(nodeRow)
                break
            }
        }
    }

    ;check that all base devices have been found
    notFoundDevs := ''
    for(dev in DevicesList.typesList)
    {
        if(dev.rowInSycon = 0)
            notFoundDevs := notFoundDevs 'Vendor: ' dev.vendor ' | Device:' dev.model '`n'
    }

    if(notFoundDevs != '')
    {
        MsgBox 'Not all devices were found in Sycon: `n' notFoundDevs
        return false
    }

    return true
}

CreateDevicesInSycon()
{
    for dev in DevicesList.typesList
    {
        ;move mouse to position
        MouseMove(mouseStartX, mouseStartY + mouseRowYOffsetPixels*dev.rowInSycon)

        ;copy and paste device
        Click_CtrlC_Click_CtrlV(dev.quantity)
    }
}

;node matches, copy it n times
Click_CtrlC_Click_CtrlV(iterations)
{
    Loop(iterations)
    {
        Sleep(SetWaitTime(3))

        MouseClick(,,,,,'D')
        Sleep(SetWaitTime(3))
        MouseClick(,,,,,'U')    
        Sleep(SetWaitTime(3))

        Send '{Ctrl Down}' 'c' '{Ctrl Up}'
        Sleep(SetWaitTime(20))

        MouseClick(,,,,,'D')
        Sleep(SetWaitTime(3))
        MouseClick(,,,,,'U')
        Sleep(SetWaitTime(10))

        Send '{Ctrl Down}' 'v' '{Ctrl Up}'
        Sleep(SetWaitTime(20))

    }
}

;next node and get symbolic name
MouseMvDn_ShiftF10_Down_Enter_ReadText(MouseYoffset := 20)
{
    MouseMove(0, 20, 0, 'R')
    Sleep(SetWaitTime(3))

    MouseClick(,,,,,'D')    
    Sleep(SetWaitTime(3))
    MouseClick(,,,,,'U')    
    Sleep(SetWaitTime(3))


    Send '{Shift Down}' '{F10}' '{Shift Up}'
    Sleep(SetWaitTime(3))

    send '{Up}'
    Sleep(SetWaitTime(3))


    Send '{Enter}'
    Sleep(SetWaitTime(3))

    Send '{Shift Down}' '{End}' '{Shift Up}'
    Sleep(SetWaitTime(3))

    Send '{Ctrl Down}' 'c' '{Ctrl Up}'
    Sleep(SetWaitTime(3))

    return A_Clipboard
}


SetWaitTime(level:=1)
{
    nLelev1Ms := 300

    return nLelev1Ms * level
}


MoveAndTrackMouseRelative(x:=0, y:=0)
{
    MouseMove(x, y, 0, 'R')

    mousePixelsMovedX+=x
    mousePixelsMovedX+=y
}



class Devices
{
    syconRows := 0
    typesList := Array()
    nodesList := Array()

    __New(){

    }

    AddType(_vendor, _device, _quantity)
    {
        this.typesList.Push(Devices.DeviceType(_vendor, _device, _quantity))
    }

    AddNode(_vendor, _model, _pnName, _ipAddress)
    {
        this.nodesList.Push(Devices.Node(_vendor, _model, _pnName, _ipAddress))
    }


    ;internal class
    class DeviceType
    {
        vendor := ""
        model := ""
        quantity := 0
        rowInSycon := 0

        __New(_vendor, _model, _quantity)
        {
            this.vendor := _vendor
            this.model := _model
            this.quantity := _quantity
        }
    }

    class Node
    {
        vendor := ""
        model := ""
        pnName := ""
        ipAddress := ""
        nodeNumber := 0

        __New(_vendor, _model, _pnName, _ipAddress)
        {
            this.vendor := _vendor
            this.model := _model
            this.pnName := _pnName
            this.ipAddress := _ipAddress
            this.nodeNumber := Integer(StrSplit(_ipAddress, '.')[4])
        }
    }
}
