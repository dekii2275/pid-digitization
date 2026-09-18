# Local model weights

This directory is deliberately excluded from Git, except for this file.

Put downloaded, trained, or exported weights here. The recommended locations
are:

```text
models/
  pretrained/          # base checkpoints, for example yolov8s.pt
  symbol-detector/     # trained checkpoints, for example best.pt
```

The current local checkpoint was moved from the former `model/` directory to
`models/symbol-detector/best.pt`. Pass its exact path to the training or
preview command; weights are not source code and must be obtained separately
when rebuilding a clone.
