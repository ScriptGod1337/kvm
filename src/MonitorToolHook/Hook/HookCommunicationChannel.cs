using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Hook {
   public class HookCommunicationChannel : MarshalByRefObject {

        public void Ping() {
            Console.WriteLine("Ping -> Pong");
        }

        public void IsInstalled(int clientPID) {
            Console.WriteLine("HookCommunicationChannel has injected into process {0}", clientPID);
        }

        public void ReportMessages(params string[] messages) {
            foreach(var msg in messages) {
                Console.WriteLine(msg);
            }
        }


    }
}
