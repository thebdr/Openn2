using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;

namespace Openn._03_ApiManager
{
    /// <summary>
    /// Dedicated backend thread for all TIA Portal Openness calls (and other
    /// long-running work such as csv loading). The Openness API is not
    /// thread-safe and its calls can take minutes, so every operation is queued
    /// and executed sequentially on this single thread - the Siemens objects are
    /// only ever touched here, while the WPF UI thread stays responsive and
    /// awaits the returned Task.
    /// </summary>
    public static class TiaWorker
    {
        private static readonly BlockingCollection<Action> workQueue = new BlockingCollection<Action>();

        /// <summary>Cancellation of the operation currently executing on the worker; null when idle.</summary>
        private static volatile CancellationTokenSource currentOperationCancellation;

        /// <summary>
        /// Token of the running operation (None when idle). Openness calls themselves
        /// cannot be interrupted, so long operations check this BETWEEN calls
        /// (per station / per module) and stop cooperatively.
        /// </summary>
        public static CancellationToken CurrentCancellation
        {
            get
            {
                CancellationTokenSource source = currentOperationCancellation;
                return source == null ? CancellationToken.None : source.Token;
            }
        }

        /// <summary>Requests cancellation of the running operation (no-op when idle).</summary>
        public static void CancelCurrentOperation()
        {
            CancellationTokenSource source = currentOperationCancellation;
            if (source != null) source.Cancel();
        }

        static TiaWorker()
        {
            var thread = new Thread(ProcessQueue)
            {
                Name = "TiaOpennessWorker",
                IsBackground = true, //must not keep the process alive on shutdown
            };
            thread.Start();
        }

        public static Task Run(Action work) =>
            Run(() => { work(); return true; });

        public static Task<T> Run<T>(Func<T> work)
        {
            //RunContinuationsAsynchronously: never resume the awaiting UI code on this thread
            var completion = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
            workQueue.Add(() =>
            {
                currentOperationCancellation = new CancellationTokenSource(); //fresh token per operation
                try { completion.SetResult(work()); }
                catch (Exception e) { completion.SetException(e); }
                finally { currentOperationCancellation = null; }
            });
            return completion.Task;
        }

        private static void ProcessQueue()
        {
            foreach (Action work in workQueue.GetConsumingEnumerable())
                work(); //exceptions are captured into the TaskCompletionSource by Run
        }
    }
}
