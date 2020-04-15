using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.Remoting;
using System.Reflection;

namespace Monitor {
    class Program {
        static void Main(string[] args) {
            string injectionLibrary = Path.Combine(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location), "Hook.dll");

            string channelName = null;
            EasyHook.RemoteHooking.IpcCreateServer<Hook.HookCommunicationChannel>(ref channelName, WellKnownObjectMode.Singleton);

            int targetPID;
            EasyHook.RemoteHooking.CreateAndInject(
                args[0], "",
                0, 
                EasyHook.InjectionOptions.DoNotRequireStrongName,
                injectionLibrary, injectionLibrary,
                out targetPID, channelName
            );

            Console.WriteLine("Created process {0}...", targetPID);

            Process.GetProcessById(targetPID).WaitForExit();

            Console.WriteLine("Press enter to exit...");
            Console.ReadLine();
        }

    }
}
