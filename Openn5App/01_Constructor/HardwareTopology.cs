using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace Openn._01_Constructor
{
    /// <summary>
    /// One PROFINET port interconnection of a station row (Stations.csv column 10 <c>Topology</c>, optional):
    /// this station's interface/port to a partner station's interface/port.
    /// </summary>
    public sealed class TopologyLink
    {
        public int OwnInterface;          //X1 -> 1
        public int OwnPort;               //P2 -> 2
        public string PartnerStation;
        public int PartnerInterface;
        public int PartnerPort;

        public string OwnDesignation => "X" + OwnInterface + "-P" + OwnPort;
        public string PartnerDesignation => "X" + PartnerInterface + "-P" + PartnerPort;
        public override string ToString() => OwnDesignation + " > " + PartnerStation + ":" + PartnerDesignation;
    }

    /// <summary>
    /// Parser of the <c>Topology</c> cell: entries separated by '|', each <c>X&lt;i&gt;-P&lt;n&gt; &gt; &lt;station&gt;:X&lt;j&gt;-P&lt;m&gt;</c>
    /// (spaces optional, case-insensitive; "->" is accepted for ">"). One side of a link is enough - the wiring
    /// pass skips a pair that is already connected. Empty cell = no links. The generation wires the links only
    /// when "Wire PROFINET ports" is ticked (TiaPortalOpenness.WirePorts).
    /// </summary>
    public static class HardwareTopology
    {
        private static readonly Regex LinkForm = new Regex(
            @"^\s*[Xx]0*(?<oi>\d+)\s*-\s*[Pp]0*(?<op>\d+)\s*(?:>|->)\s*(?<station>[^:]+?)\s*:\s*[Xx]0*(?<pi>\d+)\s*-\s*[Pp]0*(?<pp>\d+)\s*$",
            RegexOptions.Compiled);

        /// <summary>The links of a cell; every malformed entry becomes an error (with the given location prefix) and is dropped.</summary>
        public static List<TopologyLink> Parse(string cell, string where, IList<string> errors)
        {
            var links = new List<TopologyLink>();
            if (string.IsNullOrWhiteSpace(cell)) return links;

            foreach (string raw in cell.Split('|'))
            {
                string entry = raw.Trim();
                if (entry.Length == 0) continue;
                Match m = LinkForm.Match(entry);
                if (!m.Success)
                {
                    errors.Add(where + "Topology entry \"" + entry + "\" is not understood - expected X<i>-P<n> > <station>:X<j>-P<m>, e.g. X1-P2 > n0007-tric-aec01-K25102:X1-P1");
                    continue;
                }
                links.Add(new TopologyLink
                {
                    OwnInterface = int.Parse(m.Groups["oi"].Value),
                    OwnPort = int.Parse(m.Groups["op"].Value),
                    PartnerStation = m.Groups["station"].Value.Trim(),
                    PartnerInterface = int.Parse(m.Groups["pi"].Value),
                    PartnerPort = int.Parse(m.Groups["pp"].Value),
                });
            }
            return links;
        }
    }
}
