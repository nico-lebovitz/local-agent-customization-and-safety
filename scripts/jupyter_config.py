"""The workshop notebooks require the dedicated PyTorch + PEFT kernel."""
c = get_config()
c.MappingKernelManager.default_kernel_name = 'nato-course'
c.KernelSpecManager.allowed_kernelspecs = {'nato-course'}
