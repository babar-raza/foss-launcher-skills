func main() {
	if len(os.Args) < 3 {
		log.Fatalf("usage: go run ./_examples/visualtest <n1> <n2> [folder] [dpi]")
	}
	n1, err1 := strconv.Atoi(os.Args[1])
	n2, err2 := strconv.Atoi(os.Args[2])
	if err1 != nil || err2 != nil {
		log.Fatalf("n1 and n2 must be integers")
	}
	folder := ""
	if len(os.Args) > 3 {
		folder = os.Args[3]
	} else {
		folder = os.Getenv("VISUALTEST_CORPUS")
	}
	if folder == "" {
		log.Fatalf("no corpus folder: pass it as the 3rd argument or set VISUALTEST_CORPUS")
	}
	dpi := 150.0
	if len(os.Args) > 4 {
		if v, err := strconv.ParseFloat(os.Args[4], 64); err == nil && v > 0 {
			dpi = v
		}
	}

	entries, err := os.ReadDir(folder)
	if err != nil {
		log.Fatalf("read folder %q: %v", folder, err)
	}
	var files []string
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		if !strings.EqualFold(filepath.Ext(e.Name()), ".pdf") {
			continue // PDFs only
		}
		files = append(files, e.Name())
	}
	sort.Strings(files)

	if len(files) == 0 {
		fmt.Printf("no PDFs left in %s — all verified?\n", folder)
		return
	}
	if n1 < 1 {
		n1 = 1
	}
	if n2 > len(files) {
		n2 = len(files)
	}
	if n1 > n2 {
		log.Fatalf("nothing to do: %d PDF(s) left in %q, range [%d,%d]", len(files), folder, n1, n2)
	}

	outRoot := filepath.Join("result_files", "render")
	for i := n1; i <= n2; i++ {
		processOne(i, folder, files[i-1], outRoot, dpi)
	}
	fmt.Printf("done: PDFs %d..%d of %d remaining in %s → %s\n", n1, n2, len(files), folder, outRoot)
}