namespace Openn._03_ApiManager
{
    /// <summary>
    /// Lightweight description of one PLC program block, including the block group
    /// (folder) path it lives in. No Siemens types: usable by UI code and tests.
    /// </summary>
    public sealed class PlcBlockInfo
    {
        public PlcBlockInfo(string name, string blockType, string groupPath)
        {
            Name = name;
            BlockType = blockType;
            GroupPath = groupPath;
        }

        public string Name { get; }

        /// <summary>Block kind as reported by the Openness object type: FB, FC, OB, GlobalDB, InstanceDB, ...</summary>
        public string BlockType { get; }

        /// <summary>Folder path inside the program blocks tree; empty for the root, "Folder/Sub" otherwise.</summary>
        public string GroupPath { get; }

        public string DisplayText =>
            "[" + BlockType + "] " + (GroupPath.Length > 0 ? GroupPath + "/" : "") + Name;

        public override string ToString() => DisplayText;
    }
}
