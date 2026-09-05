#ifndef TRAIN_CONTROLLER_MODULE_H
#define TRAIN_CONTROLLER_MODULE_H

namespace train {

class Module {
 public:
  virtual ~Module() = default;
  virtual bool setup() = 0;
  virtual void trigger() = 0;
};

}  // namespace train

#endif
