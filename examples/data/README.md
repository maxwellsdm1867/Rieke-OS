# Local example data

Scientific recording fixtures are not included in source releases. Set
`RIEKE_TEST_MAT` to a locally exported EpicTree MAT file and `RIEKE_H5_DIR` to
its original H5 directory before running the MATLAB examples:

```matlab
setenv('RIEKE_TEST_MAT', '/path/to/local-fixtures/recordings.mat');
setenv('RIEKE_H5_DIR', '/path/to/local-fixtures/h5');
run('examples/quickstart.m');
```

Examples and real-data test scripts skip with a message when the local MAT is
unavailable. The original 0.1.0 Git history retains its historical fixtures;
0.1.1 removes them from the current index and source distribution without
rewriting history or deleting local copies.
