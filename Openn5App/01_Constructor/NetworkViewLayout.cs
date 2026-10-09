using System;
using System.Collections.Generic;
using System.Linq;

namespace Openn._01_Constructor
{
    /// <summary>
    /// The row/column plan behind "Re-arrange devices": Openness creates every station on ONE row of the
    /// network (and topology) view, in creation order, at a constant pitch, and the API offers no layout call
    /// (verified 2026-10-09: no position/layout member in Openness V15-V19, TIA's editors are invisible to UI
    /// Automation, only a mouse drag moves an object). The plan groups the stations by their Stations.csv
    /// <c>Group</c> column (the device-group path; empty = "(no group)"): a group owns one row after another,
    /// at most <see cref="MaxPerRow"/> stations per row (a longer group wraps onto the next free row); rows are
    /// handed out in the order the groups first appear in the creation order, columns = the position within the
    /// group's row. Pure arithmetic, no TIA: the window turns the cells into mouse drags from the calibrated
    /// default row, in <see cref="MovesInSafeOrder"/> - every drop must land on a free spot.
    /// </summary>
    public sealed class NetworkViewLayout
    {
        /// <summary>A station on the default row: its name and its Stations.csv Group.</summary>
        public sealed class Station
        {
            public string Name;
            public string Group;
        }

        /// <summary>One station: its default slot (Index on row 0) and its target cell.</summary>
        public sealed class Cell
        {
            public string Name;
            public string Key;
            public int Index;
            public int Row;
            public int Column;
            /// <summary>False when the target cell is the default slot (row 0, column = index).</summary>
            public bool NeedsMove => Row != 0 || Column != Index;
        }

        public const int DefaultMaxPerRow = 7;
        public const string NoGroup = "(no group)";

        public IList<Cell> Cells { get; }
        public int RowCount { get; }
        public int MaxPerRow { get; }
        public int Moves => Cells.Count(c => c.NeedsMove);

        public NetworkViewLayout(IEnumerable<Station> stationsInCreationOrder, int maxPerRow = DefaultMaxPerRow)
        {
            MaxPerRow = Math.Max(1, maxPerRow);
            var cells = new List<Cell>();
            var groupRow = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);     //the row the group is filling
            var groupColumn = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);  //the next column on that row
            int nextRow = 0;
            int index = 0;
            foreach (Station station in stationsInCreationOrder)
            {
                string key = KeyOf(station.Group);
                int column;
                if (!groupColumn.TryGetValue(key, out column) || column >= MaxPerRow)
                {
                    //the group's first station, or its row is full: the next free row is its
                    groupRow[key] = nextRow++;
                    column = 0;
                }
                cells.Add(new Cell { Name = station.Name, Key = key, Index = index, Row = groupRow[key], Column = column });
                groupColumn[key] = column + 1;
                index++;
            }
            Cells = cells;
            RowCount = nextRow;
        }

        /// <summary>The row key of a station: its Group as written in Stations.csv, "(no group)" when empty.</summary>
        public static string KeyOf(string group) =>
            string.IsNullOrWhiteSpace(group) ? NoGroup : group.Trim();

        /// <summary>
        /// The moves in an order where every drop lands on a free spot: first every station bound for a row
        /// below the default row (those rows are empty), then the stations that stay on row 0, compacted left to
        /// right - by then the slots they move into have been vacated by stations that went down (or by row-0
        /// stations already compacted further left).
        /// </summary>
        public IEnumerable<Cell> MovesInSafeOrder()
        {
            foreach (Cell cell in Cells.Where(c => c.NeedsMove && c.Row > 0)) yield return cell;
            foreach (Cell cell in Cells.Where(c => c.NeedsMove && c.Row == 0).OrderBy(c => c.Column)) yield return cell;
        }

        /// <summary>One line per row: "row 2 (=TRIC_IODevices, continued): n0013-..., n0014-..." with a note for the row that stays.</summary>
        public IEnumerable<string> Describe()
        {
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var group in Cells.GroupBy(c => c.Row).OrderBy(g => g.Key))
            {
                string key = group.First().Key;
                bool continued = !seen.Add(key);
                yield return "row " + (group.Key + 1) + " (" + key + (continued ? ", continued" : string.Empty) + "): " +
                             string.Join(", ", group.OrderBy(c => c.Column).Select(c => c.Name)) +
                             (group.Key == 0 ? (group.Any(c => c.NeedsMove) ? "  - the default row, compacted last" : "  - stays on the default row") : string.Empty);
            }
        }
    }
}
