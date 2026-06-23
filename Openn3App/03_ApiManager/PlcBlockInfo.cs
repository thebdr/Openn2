namespace Openn._03_ApiManager
{
    /// <summary>
    /// Lightweight description of one PLC program block (or PLC data type), including
    /// the group (folder) path it lives in and its programming language. No Siemens
    /// types: usable by UI code and tests.
    /// </summary>
    public sealed class PlcBlockInfo
    {
        public PlcBlockInfo(string name, string blockType, string groupPath, string language, bool isType = false)
        {
            Name = name;
            BlockType = blockType;
            GroupPath = groupPath;
            Language = language ?? "";
            IsType = isType;
        }

        public string Name { get; }

        /// <summary>Block kind as reported by the Openness object type: FB, FC, OB, GlobalDB, InstanceDB, UDT, ...</summary>
        public string BlockType { get; }

        /// <summary>Folder path inside the tree; empty for the root, "Folder/Sub" otherwise.</summary>
        public string GroupPath { get; }

        /// <summary>Programming language (LAD, FBD, SCL, STL, DB, F_LAD, ...); empty for data types.</summary>
        public string Language { get; }

        /// <summary>True for PLC data types (UDTs), which live in the type group, not the block group.</summary>
        public bool IsType { get; }

        public string DisplayText =>
            "[" + BlockType + (Language.Length > 0 ? " | " + Language : "") + "] " +
            (GroupPath.Length > 0 ? GroupPath + "/" : "") + Name;

        public override string ToString() => DisplayText;
    }
}
