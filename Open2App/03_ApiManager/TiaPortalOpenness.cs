using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using Siemens.Engineering;
using static Openn._10_StandardFunctions.LogsManager;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// Facade over the Siemens TIA Portal Openness API. One instance is created by
    /// the main window and holds the connection state (portal + project) for the
    /// lifetime of the application.
    ///
    /// The class is split across partial files by feature area:
    ///   TiaPortalOpenness.cs          - portal/project lifecycle (this file)
    ///   TiaPortalOpenness.Blocks.cs   - program block listing, export and import
    ///   TiaPortalOpenness.Hardware.cs - hardware generation from the csv configuration
    /// Custom parameter writing lives in its own class (CustomParameterApplier).
    ///
    /// Threading rule: every method of this class must be invoked on the TiaWorker
    /// thread (the Openness API is not thread-safe) - UI code queues calls via
    /// TiaWorker.Run(...) and never touches this class directly.
    /// </summary>
    public partial class TiaPortalOpenness
    {
        #region Connection state

        /// <summary>Folder of the running exe; used for default project/export paths.</summary>
        private readonly string appBaseDir = Path.GetDirectoryName(Process.GetCurrentProcess().MainModule.FileName);

        /// <summary>
        /// The portal instance this app started or attached to. Kept referenced for
        /// the whole session - dropping it would let the Openness connection die.
        /// </summary>
        private TiaPortal portal = null;

        /// <summary>The project all block and hardware operations work on; null = not attached.</summary>
        private Project project = null;

        #endregion Connection state

        #region Attach / detach

        /// <summary>
        /// Binds this instance to a TIA project, trying in order:
        /// 1. no path given - create a fresh timestamped project under appBaseDir\TiaProjects,
        /// 2. a running Tia Portal instance that already has the project open,
        /// 3. open the project file (*.ap18/.ap19/...) in a new Tia Portal with UI.
        /// Returns the project name, or "" on failure.
        /// </summary>
        public string AttachToProject(string _Path = "")
        {
            bool bCreateNewProject = string.IsNullOrEmpty(_Path); //if no path is specified, create a new project
            string defaultProjectsFolder = appBaseDir + "\\TiaProjects\\";
            string projectName = "openness_project";
            string projectPath = defaultProjectsFolder + projectName;

            if (!bCreateNewProject)
            {
                projectPath = _Path;
                projectName = new DirectoryInfo(projectPath).Name;

                project = TryAttachToOpenProject(projectPath);
                if (project == null)
                    Log("Project is not open");
            }

            try
            {
                if (bCreateNewProject)
                {
                    projectName += "_" + DateTime.Now.ToString("yyyyMMdd_HHmmss");

                    if (Directory.Exists(defaultProjectsFolder + projectName))
                    {
                        try
                        {
                            Directory.Delete(defaultProjectsFolder + projectName, true);
                            Log("TIA PROJECT DELETED: " + defaultProjectsFolder + projectName);
                        }
                        catch (Exception e)
                        {
                            Log("TIA PROJECT DELETE ERROR \n" + e.Message);
                        }
                    }

                    portal = new TiaPortal(TiaPortalMode.WithUserInterface);
                    project = portal.Projects.Create(new DirectoryInfo(defaultProjectsFolder), projectName);

                    Log("Attached to New Tia Project: " + project.Name);
                }
                else if (project == null) //not open in any running instance: open it in a new Tia Portal
                {
                    FileInfo projectFile = FindProjectFile(projectPath);
                    if (projectFile == null)
                    {
                        Log("ERROR Attaching Tia Project \nNo TIA project file (*" +
                            OpennessSetup.SelectedInstallation.ProjectFileExtension + ", *.ap..) found in: " + projectPath);
                        return "";
                    }

                    portal = new TiaPortal(TiaPortalMode.WithUserInterface);
                    project = portal.Projects.Open(projectFile);
                    Log("Opened Tia Project: " + projectFile.Name);
                }

                return project.Name;
            }
            catch (Exception e)
            {
                Log("ERROR Attaching Tia Project \n" + e.Message);
                return "";
            }
        }

        /// <summary>
        /// Attaches to a running Tia Portal instance that has the given project open.
        /// Returns null when no such instance exists.
        /// </summary>
        private Project TryAttachToOpenProject(string projectPath)
        {
            foreach (TiaPortalProcess tiaPortalProcess in TiaPortal.GetProcesses())
            {
                if (TiaWorker.CurrentCancellation.IsCancellationRequested)
                {
                    Log("Attach CANCELLED");
                    return null;
                }

                try
                {
                    if (tiaPortalProcess.ProjectPath == null) continue;
                    if (!tiaPortalProcess.ProjectPath.ToString().Contains(projectPath)) continue;

                    portal = TiaPortal.GetProcess(tiaPortalProcess.Id).Attach(); //keep the attached instance referenced
                    foreach (Project openProject in portal.Projects)
                    {
                        Log("Attached to Existing Tia Project: " + openProject.Name);
                        return openProject;
                    }
                }
                catch (Exception e)
                {
                    Log("ERROR attaching to Tia Portal process [" + tiaPortalProcess.Id + "] \n" + e.Message);
                }
            }
            return null;
        }

        /// <summary>
        /// Finds the project file (*.ap18, *.ap19, ...) inside the project folder,
        /// preferring the extension that matches the selected Tia Portal version.
        /// </summary>
        private FileInfo FindProjectFile(string projectDirectory)
        {
            var directory = new DirectoryInfo(projectDirectory);
            if (!directory.Exists) return null;

            var candidates = directory.GetFiles("*.ap*").Where(IsTiaProjectFile).ToList();
            if (candidates.Count == 0) return null;

            string preferredExtension = OpennessSetup.SelectedInstallation.ProjectFileExtension;
            return candidates.FirstOrDefault(f => f.Extension.Equals(preferredExtension, StringComparison.OrdinalIgnoreCase))
                   ?? candidates[0];
        }

        private static bool IsTiaProjectFile(FileInfo file)
        {
            string extension = file.Extension; //".ap18", ".ap15_1", ...
            if (extension.Length <= 3 || !extension.StartsWith(".ap", StringComparison.OrdinalIgnoreCase)) return false;
            return extension.Substring(3).All(c => char.IsDigit(c) || c == '_');
        }

        /// <summary>
        /// Forgets the attached project (the Tia Portal itself keeps running).
        /// Returns "" so callers can clear the project display directly.
        /// </summary>
        public string DetachProject()
        {
            if (project == null)
            {
                Log("Can't detach: No Tia Project attached");
            }
            else
            {
                Log("Tia Project detached: " + project.Name);
                project = null;
            }
            return "";
        }

        private void SaveProject()
        {
            if (project != null)
            {
                project.Save();
                Log("Project Save Ok: " + project.Name + " has been saved");
            }
        }

        #endregion Attach / detach

        #region Running instances

        /// <summary>Snapshot of one running Tia Portal process, for the instances dropdown.</summary>
        public struct TiaProcessInfo
        {
            public string ProcessID;
            public string ProcessPath;
            public string ProjectPath;
            public string ProjectName;

            public TiaProcessInfo(string _ProcessID, string _ProcessPath, string _ProjectPath, string _ProjectName)
            {
                ProcessID = _ProcessID;
                ProcessPath = _ProcessPath;
                ProjectPath = _ProjectPath;
                ProjectName = _ProjectName;
            }
        }

        /// <summary>
        /// Lists the Tia Portal processes currently running on this machine.
        /// Requires membership in the "Siemens TIA Openness" Windows group.
        /// </summary>
        public IList<TiaProcessInfo> GetOpenTiaInstances()
        {
            TiaProcessInfo processInfo = new TiaProcessInfo();
            IList<TiaProcessInfo> processInfoList = new List<TiaProcessInfo>();
            foreach (TiaPortalProcess tiaPortalProcess in TiaPortal.GetProcesses())
            {
                try
                {
                    processInfo.ProcessID = tiaPortalProcess.Id.ToString();
                    processInfo.ProcessPath = tiaPortalProcess.Path.ToString();
                    processInfo.ProjectPath = tiaPortalProcess.ProjectPath != null ? tiaPortalProcess.ProjectPath.ToString() : "No Project";
                    processInfo.ProjectName = new DirectoryInfo(processInfo.ProjectPath).Name.ToString();

                    processInfoList.Add(processInfo);
                }
                catch (Exception e)
                {
                    Log("Error getting Tia Portal Process Information \n" + e.Message);
                }
            }
            return processInfoList;
        }

        #endregion Running instances
    }
}
