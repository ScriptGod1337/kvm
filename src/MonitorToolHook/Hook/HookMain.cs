using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Runtime.InteropServices;

namespace Hook {
    public class HookMain : EasyHook.IEntryPoint {
        private HookCommunicationChannel channel;
        private List<EasyHook.LocalHook> hooks = new List<EasyHook.LocalHook>();
        private BlockingCollection<String> msgQueue = new BlockingCollection<string>();

        public HookMain(EasyHook.RemoteHooking.IContext context, string channelName) {
            channel = EasyHook.RemoteHooking.IpcConnectClient<HookCommunicationChannel>(channelName);
        }

        public void Run(EasyHook.RemoteHooking.IContext context, string channelName) {
            channel.IsInstalled(EasyHook.RemoteHooking.GetCurrentProcessId());

            hooks.Add(HookAPI("dxva2.dll", "GetVCPFeatureAndVCPFeatureReply", new GetVCPFeatureAndVCPFeatureReply_Delegate(GetVCPFeatureAndVCPFeatureReply_Hook)));
            hooks.Add(HookAPI("dxva2.dll", "SetVCPFeature", new SetVCPFeature_Delegate(SetVCPFeature_Hook)));

            channel.ReportMessages(String.Format("Hook active. Starting application...", EasyHook.RemoteHooking.GetCurrentProcessId()));
            EasyHook.RemoteHooking.WakeUpProcess();

            try {
                while (true) {
                    String msg;
                    if (msgQueue.TryTake(out msg, TimeSpan.FromMilliseconds(5000))) {
                        channel.ReportMessages(msg);
                    } else {
                        channel.Ping();
                    }
                }
            } finally {
                foreach (var hook in hooks) {
                    hook.Dispose();
                }
                EasyHook.LocalHook.Release();
            }
        }

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr LoadLibrary(string dllName);

        private EasyHook.LocalHook HookAPI(String dllName, String Method, Delegate InNewProck) {
            // ensure thate the dll is loaded
            LoadLibrary(dllName);

            // hock
            var hook = EasyHook.LocalHook.Create(
              EasyHook.LocalHook.GetProcAddress(dllName, Method),
              InNewProck, this);
            hook.ThreadACL.SetExclusiveACL(new Int32[] { 0 });

            msgQueue.Add(String.Format("Hooked {0} {1}", dllName, Method));
            return hook;
        }

        #region GetVCPFeatureAndVCPFeatureReply
        [DllImport("dxva2.dll", SetLastError = true)]
        private static extern Boolean GetVCPFeatureAndVCPFeatureReply(IntPtr hMonitor, byte bVCPCode, IntPtr pvct, IntPtr pdwCurrentValue, IntPtr pdwMaximumValue);

        [UnmanagedFunctionPointer(CallingConvention.StdCall, SetLastError = true)]
        private delegate Boolean GetVCPFeatureAndVCPFeatureReply_Delegate(IntPtr hMonitor, byte bVCPCode, IntPtr pvct, IntPtr pdwCurrentValue, IntPtr pdwMaximumValue);

        private Boolean GetVCPFeatureAndVCPFeatureReply_Hook(IntPtr hMonitor, byte bVCPCode, IntPtr pvct, IntPtr pdwCurrentValue, IntPtr pdwMaximumValue) {
            Boolean result = GetVCPFeatureAndVCPFeatureReply(hMonitor, bVCPCode, pvct, pdwCurrentValue, pdwMaximumValue);
            if (result) {
                msgQueue.Add(String.Format("**read  OK GetVCPFeatureAndVCPFeatureReply_Hook 0x{0:X} 0x{1:X} 0x{2:X} 0x{3:X}", hMonitor, bVCPCode,
                    Marshal.ReadInt32(pdwCurrentValue), Marshal.ReadInt32(pdwMaximumValue)));
            } else {
                msgQueue.Add(String.Format("**read NOK GetVCPFeatureAndVCPFeatureReply_Hook 0x{0:X} 0x{1:X}", hMonitor, bVCPCode));
            }
            return result;
        }
        #endregion

        #region SetVCPFeature
        [DllImport("dxva2.dll", SetLastError = true)]
        private static extern Boolean SetVCPFeature(IntPtr hMonitor, byte bVCPCode, UInt32 dwNewValue);

        [UnmanagedFunctionPointer(CallingConvention.StdCall, SetLastError = true)]
        private delegate Boolean SetVCPFeature_Delegate(IntPtr hMonitor, byte bVCPCode, UInt32 dwNewValue);

        private Boolean SetVCPFeature_Hook(IntPtr hMonitor, byte bVCPCode, UInt32 dwNewValue) {
            msgQueue.Add(String.Format("**write SetcVCPFeature 0x{0:X} 0x{1:X} 0x{2:X}", hMonitor, bVCPCode, dwNewValue));
            return SetVCPFeature(hMonitor, bVCPCode, dwNewValue);
        }
        #endregion
    }
}
