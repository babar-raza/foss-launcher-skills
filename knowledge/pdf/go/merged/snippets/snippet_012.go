func main() {
	// Parse args: an optional --recurse flag (in any position) plus the
	// target folder. Kept hand-rolled to avoid a flag-package dependency.
	var dir string
	var recurse bool
	for _, a := range os.Args[1:] {
		switch a {
		case "--recurse", "-recurse":
			recurse = true
		default:
			if dir == "" {
				dir = a
			}
		}
	}
	if dir == "" {
		fmt.Fprintln(os.Stderr, "usage: go run ./_examples/openall [--recurse] <folder>")
		os.Exit(2)
	}

	files, err := collectPDFs(dir, recurse)
	if err != nil {
		fmt.Fprintf(os.Stderr, "scan %q: %v\n", dir, err)
		os.Exit(1)
	}
	sort.Strings(files)

	if len(files) == 0 {
		fmt.Printf("No .pdf files found in %q\n", dir)
		return
	}
	scope := "in"
	if recurse {
		scope = "under"
	}
	fmt.Printf("Opening %d PDF file(s) %s %s\n", len(files), scope, dir)
	fmt.Printf("Passwords tried on encrypted files: %v\n\n", passwordsToTry)

	var results []result
	var nOK, nPW, nLocked, nErr, nPanic int
	for _, f := range files {
		r := openOne(f)
		results = append(results, r)
		switch r.status {
		case "ok":
			nOK++
		case "ok-pw":
			nPW++
		case "locked":
			nLocked++
		case "error":
			nErr++
		case "panic":
			nPanic++
		}
	}

	for _, r := range results {
		name := filepath.Base(r.path)
		switch r.status {
		case "ok":
			fmt.Printf("  OK        %-40s %d page(s)  %v\n", name, r.pages, r.elapsed.Round(time.Millisecond))
		case "ok-pw":
			fmt.Printf("  OK (pw)   %-40s %d page(s)  password=%q\n", name, r.pages, r.password)
		case "locked":
			fmt.Printf("  LOCKED    %-40s (encrypted — none of %v worked)\n", name, passwordsToTry)
		case "error":
			fmt.Printf("  ERROR     %-40s %s\n", name, r.detail)
		case "panic":
			fmt.Printf("  PANIC     %-40s %s\n", name, r.detail)
		}
	}

	fmt.Printf("\nSummary: %d ok, %d ok-with-password, %d locked, %d error, %d panic  (of %d)\n",
		nOK, nPW, nLocked, nErr, nPanic, len(files))

	if nErr > 0 || nPanic > 0 {
		fmt.Println("\nFailures:")
		for _, r := range results {
			if r.status == "error" || r.status == "panic" {
				fmt.Printf("  [%s] %s\n      %s\n", strings.ToUpper(r.status), r.path, r.detail)
			}
		}
		os.Exit(1)
	}
}