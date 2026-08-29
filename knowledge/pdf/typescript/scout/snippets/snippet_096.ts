it('searches the TEXT of /RC, not its markup', () => {
    // The defect this closes: the entry holds an XHTML fragment, so a query for
    // the words a reader sees found nothing.
    const hits = rcDoc('<body><p>the report</p></body>').Pages[0]
      .SearchAnnotationText('the report');
    expect(hits).toHaveLength(1);
    expect(hits[0].key).toBe('RC');
    expect(hits[0].text).toBe('the report');
  })