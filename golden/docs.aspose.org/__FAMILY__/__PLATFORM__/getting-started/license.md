<!-- GOLDEN REFERENCE | Structural Exemplar | Language: Python (structural only) | Original-Grade: C→A -->
---
title: Metered Licensing
description: >-
  Learn how to use {{PRODUCT_NAME}} to apply a metered licensing key
weight: 15
type: docs
---

{{PRODUCT_NAME}} implements a metered licensing mechanism. This flexible approach allows you to utilize features based on your specific needs while maintaining compliance with licensing terms.

## Key Features of the Metered Licensing Model

- **Single License Per Instance**: Each application instance can only license one module. If you attempt to access features outside the licensed scope, your application will automatically switch to trial mode.
- **Trial Mode**: Experience the benefits of the library without upfront costs. This mode allows exploration of additional features, providing a risk-free opportunity to assess the software.

To purchase licenses, visit the [Purchase Portal](https://purchase.aspose.net/{{PRODUCT_FAMILY}}).

## How to Implement Metered Licensing

Follow this step-by-step guide to configure metered licensing for your application:

1. **Create a License Instance**: Create an instance of the metered license class.
2. **Set Your Keys**: Use the `set_metered_key` method to enter your public and private keys.
3. **Perform Processing Tasks**: Execute the necessary tasks using the library.
4. **Monitor Consumption**: Utilize the `get_consumption_quantity` method to track the total number of API requests consumed.

### Example of Metered Licensing Implementation

Here's a practical example demonstrating how to set your metered keys:

```python
import library

license = library.MeteredLicense()
license.set_metered_key("<your public key>", "<your private key>")
```

For additional examples and detailed usage, refer to the [Developer Guide](/docs/{{PRODUCT_FAMILY}}/developer-guide/).

## Benefits of Metered Licensing

- **Cost-Effective**: Pay only for the features you actually use, reducing overall costs.
- **Scalability**: Easily adjust your licensing as your application requirements evolve.
- **Transparency**: Monitor your usage with the `get_consumption_quantity` method to understand how much you're consuming.
- **Flexibility**: Explore additional features in trial mode before making a purchase decision.
