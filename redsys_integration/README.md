# Odoo Redsys & Bizum Payment Integration

This Odoo module integrates the Redsys payment gateway, allowing you to seamlessly accept payments via credit/debit cards and Bizum directly within your Odoo e-commerce and accounting environment.

## Features
- **Credit & Debit Card Payments**: Standard Redsys payment gateway integration.
- **Bizum Payments**: Built-in support for Bizum, a widely used mobile payment method in Spain.
- **Payment Tracking**: Full tracking of payment status directly within the Odoo backend.
- **Tokenization Support**: Capability to securely save card tokens for future and automatic payments (requires support from your Redsys merchant account).

## Installation
1. Clone or download this repository into your Odoo `addons` directory.
2. Update your Odoo app list.
3. Search for "Pago por Redsys / Bizum" and click **Install**.

## Configuration
To configure the payment gateway:
1. Navigate to **Accounting** (or **Website**) **> Configuration > Payment Providers**.
2. Locate and open the **Redsys** or **Bizum** provider.
3. Change the State to `Test Mode` or `Enabled` (Production).
4. Enter the credentials provided by your bank/Redsys:
   - **Merchant Name** (Nombre del Comercio)
   - **Merchant Code (FUC)**
   - **Secret Key** 
   - **Terminal** (Defaults to 1)
5. Save your changes and publish the payment method to make it available during checkout.

## Technical Details
- **Dependencies**: Requires Odoo `payment` and `website_sale` modules.
- **Security**: Utilizes Redsys HMAC SHA256 V1 signature requirements for secure server-to-server communication.