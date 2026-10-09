using System;
using System.Collections.Generic;
using System.Linq;

namespace Openn._01_Constructor
{
    /// <summary>
    /// The row/column plan behind "Re-arrange devices": Openness creates every station on ONE row of the
    /// network (and topology) view, in creation order, at a constant pitch, and the API offers no layout call
    /// (verified 2026-10-09: no position/layout member in Openness V15-V19, TIA's editors are invisible to UI
    /// Automation, only a mouse drag moves an object). So the plan keys each station by the middle dash
    /// segments of its name (n0006-tric-aec01-K25101 -> "tric-aec01"; fewer than three segments = the whole
    /// name) and makes every RUN of consecutive equal keys one row, in creation order; the column is the
    /// position within the run. Row 0 therefore never moves (its columns equal the default slots); the other
    /// rows are empty space below the default row, so every drag lands on a free cell. Pure arithmetic, no TIA:
    /// the window turns the cells into mouse drags from the calibrated default row.
    /// </summary>
    public sealed class NetworkViewLayout
    {
        /// <summary>One station: its default slot (Index on row 0) and its target cell.</summary>
        public sealed class Cell
        {
            public string Name;
            public string Key;
            public int Index;
            public int Row;
            public int Column;
            /// <summary>False for row 0: a station on the first run already sits where it belongs.</summary>
            public bool NeedsMove => Row != 0 || Column != Index;
        }

        public IList<Cell> Cells { get; }
        public int RowCount { get; }
        public int Moves => Cells.Count(c => c.NeedsMove);

        public NetworkViewLayout(IEnumerable<string> stationsInCreationOrder)
        {
            var cells = new List<Cell>();
            int row = -1, column = 0;
            string previousKey = null;
            int index = 0;
            foreach (string name in stationsInCreationOrder)
            {
                string key = KeyOf(name);
                if (row < 0 || !string.Equals(key, previousKey, StringComparison.OrdinalIgnoreCase))
                {
                    row++;
                    column = 0;
                    previousKey = key;
                }
                cells.Add(new Cell { Name = name, Key = key, Index = index, Row = row, Column = column });
                index++;
                column++;
            }
            Cells = cells;
            RowCount = row + 1;
        }

        /// <summary>The row key of a station name: the dash segments between the first and the last one.</summary>
        public static string KeyOf(string name)
        {
            string[] parts = (name ?? string.Empty).Split('-');
            if (parts.Length < 3) return name ?? string.Empty;
            return string.Join("-", parts, 1, parts.Length - 2);
        }

        /// <summary>One line per row: "row 2 (lb-ae01): n0023-lb-ae01-K30001, n0030-lb-ae02-K30001".</summary>
        public IEnumerable<string> Describe()
        {
            foreach (var group in Cells.GroupBy(c => c.Row).OrderBy(g => g.Key))
                yield return "row " + (group.Key + 1) + " (" + group.First().Key + "): " + string.Join(", ", group.Select(c => c.Name)) +
                             (group.Key == 0 ? "  - stays on the default row" : string.Empty);
        }
    }
}
