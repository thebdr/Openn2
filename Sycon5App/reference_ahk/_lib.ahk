#Requires AutoHotkey v2.0

/* -------------------------------------------------------------
    Moves the cursor holding Shift numChars times.
    With dir positive to the right, else to the left
+ ------------------------------------------------------------*/
MoveSelection(numChars, dir := 1)
{
    Send "{Shift DOWN}"

    if (dir >= 0) {
        Send "{Right " numChars "}"
    } else {
        Send "{Left " numChars "}"
    }

    Send "{Shift UP}"
}

/* -------------------------------------------------------------
    Reads a variable number of chars moving left from the cursor
    and return the selection as text. Stops at stopChar
+ ------------------------------------------------------------*/
ReadTextBackwards(maxChars := 16, stopChar := "<") 
{
    selectedText := ""

    loop maxChars
    {
        MoveSelection(1, -1)
        selectedText := ReadSelection().text

        if (SubStr(selectedText, 1,1) = stopChar)
        {
            return selectedText
        }
    }    
    
    return selectedText
}


/* -------------------------------------------------------------
    read selection by copying to clipboard (Ctrl+C) adn reading
    the clipboard. Other methods do not always work.
+ ------------------------------------------------------------*/
ReadSelection(keepClipboardData := false)
{
    retData := {method : "", text : "", anomaly : ""}

    if (keepClipboardData)
    {
        oldClipboard := ClipboardAll()
    }

    A_Clipboard := "" ;clean clipboard

    Send "^c" ;copy selection
    if !ClipWait(2)
    {
        retData.anomaly := "Clipboard Timeout"
        return retData
    }

    retData.text := A_Clipboard
    retData.method := "clipboard"

    if (keepClipboardData)
    {
        A_Clipboard := oldClipboard
        oldClipboard := ""
    }          

    return retData
}


/* -------------------------------------------------------------
    check if a 1 dimensional array contains a value
+ ------------------------------------------------------------*/
ArrayContains(value, _array)
{
    for n, v in _array
    {
        if (value = v)
        {
            return true
        }
    }

    return false

}


/* -------------------------------------------------------------
    simulate a key press for every character in the string
+ ------------------------------------------------------------*/
SendStringKeyByKey(str)
{
    i:=0
    while(i<StrLen(str))
    {
        i++
        Send SubStr(str, i, 1)
    }

}

/* -------------------------------------------------------------
    precede RegEx reverved chars with a '\'
+ ------------------------------------------------------------*/
EscapeRegExSpecialChars(strg)
{
    specialChars := [".", "^", "$", "*", "+", "-", "?", "(", ")", "[", "]", "{", "}", "\", "|"]
    retStr := ""


    Loop(StrLen(strg))
    {
        char := SubStr(strg, A_Index, 1)
        if(ArrayContains(char, specialChars))
        {
            retStr := retStr '\' char
        }
        else
        {
            retStr := retStr char
        }
    }

    return retStr

}