[Test, Ignore("Not a Test")]
        [JavaDelete]
        public void CheckCLRVersion()
        {
            // Test one
            Console.WriteLine("CLR Version: {0}", Environment.Version.ToString());
        }