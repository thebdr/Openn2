using System;
using System.Collections.Generic;
using System.IO;
using Siemens.Engineering;
using Siemens.Engineering.HW;
using Siemens.Engineering.HW.Features;
using Siemens.Engineering.SW;
using Siemens.Engineering.SW.Blocks;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// Program block operations: listing the whole block tree (used by the block
    /// search window), exporting a block to xml and importing an xml block file.
    /// </summary>
    public partial class TiaPortalOpenness
    {
        /// <summary>
        /// Exports the named block as xml into appBaseDir\ExportedBlocks. The block
        /// is searched in the whole program blocks tree, subfolders included.
        /// </summary>
        public void ExportBlock(string blockName)
        {
            if (project == null)
            {
                Log("Can't export: No Tia Project Attached");
                return;
            }
            PlcSoftware plcSoftware = GetPlcSoftware(project);
            if (plcSoftware == null)
            {
                Log("Can't export: no Plc Software found in the project");
                return;
            }

            PlcBlock plcBlock = FindBlock(plcSoftware.BlockGroup, blockName);
            if (plcBlock == null)
            {
                Log("ERROR Exporting Block \nBlock not found: " + blockName);
                return;
            }

            try
            {
                var exportFile = new FileInfo(appBaseDir + "\\ExportedBlocks\\" + plcBlock.Name + ".xml");
                exportFile.Directory.Create(); //no-op when it already exists
                plcBlock.Export(exportFile, ExportOptions.WithDefaults);
                Log("Exported software block: " + plcBlock.Name);
            }
            catch (Exception e)
            {
                Log("ERROR Exporting Source Block \n" + e.Message);
            }
        }

        /// <summary>
        /// Imports an xml block file into the root block group of the Plc program,
        /// overriding an existing block with the same name.
        /// </summary>
        public void ImportPlcBlock(string fileName)
        {
            try
            {
                PlcSoftware plcSoftware = GetPlcSoftware(project);
                {
                    PlcBlockGroup blockGroup = plcSoftware.BlockGroup;
                    IList<PlcBlock> blocks = blockGroup.Blocks.Import(new
                         FileInfo(fileName), ImportOptions.Override);
                }
                Log("Plc Source Block : " + fileName + " imported successfully");
            }
            catch (Exception e)
            {
                Log("ERROR Importing Plc Block \n" + e.Message);
            }
        }

        /// <summary>
        /// All program blocks of the attached project, including blocks inside
        /// block groups (subfolders) at any depth, sorted by display text.
        /// </summary>
        public IList<PlcBlockInfo> GetAllBlocks()
        {
            var blocks = new List<PlcBlockInfo>();

            if (project == null)
            {
                Log("Can't read blocks: No Tia Project Attached");
                return blocks;
            }
            PlcSoftware plcSoftware = GetPlcSoftware(project);
            if (plcSoftware == null)
            {
                Log("Can't read blocks: no Plc Software found in the project");
                return blocks;
            }

            CollectBlocks(plcSoftware.BlockGroup, "", blocks);
            blocks.Sort((a, b) => string.Compare(a.DisplayText, b.DisplayText, StringComparison.OrdinalIgnoreCase));

            Log("Software blocks list refreshed: found " + blocks.Count + " block(s)");
            return blocks;
        }

        /// <summary>Depth-first walk of a block group, accumulating blocks with their folder path.</summary>
        private void CollectBlocks(PlcBlockGroup group, string groupPath, List<PlcBlockInfo> blocks)
        {
            foreach (PlcBlock block in group.Blocks)
                blocks.Add(new PlcBlockInfo(block.Name, block.GetType().Name, groupPath));

            foreach (PlcBlockUserGroup subGroup in group.Groups)
                CollectBlocks(subGroup, groupPath.Length == 0 ? subGroup.Name : groupPath + "/" + subGroup.Name, blocks);
        }

        /// <summary>Finds a block by name anywhere in the program blocks tree (names are unique per Plc).</summary>
        private PlcBlock FindBlock(PlcBlockGroup group, string blockName)
        {
            PlcBlock block = group.Blocks.Find(blockName);
            if (block != null) return block;

            foreach (PlcBlockUserGroup subGroup in group.Groups)
            {
                block = FindBlock(subGroup, blockName);
                if (block != null) return block;
            }
            return null;
        }

        /// <summary>
        /// The Plc program of the first device in the project that exposes a
        /// software container (this tool targets single-Plc projects).
        /// </summary>
        private PlcSoftware GetPlcSoftware(Project _project)
        {
            PlcSoftware plcSoftware = null;
            foreach (Device device in _project.Devices)
            {
                DeviceItemComposition deviceItemComposition = device.DeviceItems;
                foreach (DeviceItem _deviceItem in deviceItemComposition)
                {
                    SoftwareContainer softwareContainer = _deviceItem.GetService<SoftwareContainer>();
                    if (softwareContainer != null)
                    {
                        Software softwareBase = softwareContainer.Software;
                        plcSoftware = softwareBase as PlcSoftware;
                        if (plcSoftware != null)
                        {
                            break;
                        }
                    }
                }
                break; //only the first device is inspected
            }
            return plcSoftware;
        }
    }
}
