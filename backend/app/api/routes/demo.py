from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

DEMO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TestMate AI - Demo Storefront</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 24px; color: #1e293b; background: #f8fafc; }
    .card { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    h1 { color: #0f172a; margin-top: 0; }
    h2 { color: #334155; margin-top: 0; }
    .product { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #f1f5f9; }
    .price { font-weight: bold; color: #059669; font-size: 1.1em; }
    button { background: #2563eb; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 500; font-size: 14px; }
    button:hover { background: #1d4ed8; }
    .cart-badge { background: #e0e7ff; color: #3730a3; padding: 4px 10px; border-radius: 9999px; font-weight: 600; font-size: 14px; }
    .form-group { margin-bottom: 14px; }
    label { display: block; margin-bottom: 4px; font-weight: 500; font-size: 14px; }
    input[type="text"], input[type="number"] { width: 100%; padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 6px; box-sizing: border-box; }
    .checkbox-group { display: flex; align-items: center; gap: 8px; margin: 12px 0; }
    .alert { padding: 16px; border-radius: 6px; margin-top: 16px; display: none; font-weight: 500; }
    .alert-success { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
    .alert-error { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }
  </style>
</head>
<body>
  <h1>TestMate AI Sample Store</h1>
  <p>Isolated local demonstration storefront for automated browser testing.</p>

  <div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <h2>Available Products</h2>
      <div>Cart Items: <span id="cart-count" class="cart-badge" data-testid="cart-count">0</span></div>
    </div>

    <div class="product">
      <div>
        <strong id="product-name">Autonomous Test Runner Pro</strong>
        <div style="color: #64748b; font-size: 13px;">Enterprise autonomous testing subscription</div>
      </div>
      <div>
        <span class="price">$49.99</span>
        <button type="button" id="add-to-cart-btn" data-testid="add-cart-btn" onclick="addToCart()">Add to Cart</button>
      </div>
    </div>
  </div>

  <div class="card" id="checkout-section">
    <h2>Secure Checkout</h2>
    <form id="checkout-form" onsubmit="event.preventDefault(); submitOrder();">
      <div class="form-group">
        <label for="name">Cardholder Name</label>
        <input type="text" id="name" name="name" placeholder="John Doe" required>
      </div>

      <div class="form-group">
        <label for="card">Card Number</label>
        <input type="text" id="card" name="card" placeholder="4242 4242 4242 4242" required>
      </div>

      <div class="form-group">
        <label for="qty">Quantity</label>
        <input type="number" id="qty" name="qty" value="1" min="1" max="10" required>
      </div>

      <div class="checkbox-group">
        <input type="checkbox" id="terms" name="terms" required checked>
        <label for="terms" style="margin: 0; font-weight: normal;">I agree to the test terms and conditions</label>
      </div>

      <button type="submit" id="submit-order-btn" data-testid="submit-btn" style="width: 100%; padding: 12px;">Place Order</button>
    </form>

    <div id="confirmation-alert" class="alert alert-success" data-testid="confirmation-msg">
      Order Confirmed! Your purchase of Autonomous Test Runner Pro has been processed successfully. Confirmation #TM-99210.
    </div>

    <div id="error-alert" class="alert alert-error" data-testid="error-msg">
      Payment failed: Gateway rejected transaction. Check card number or balance.
    </div>
  </div>

  <script>
    let cartItems = 0;

    function addToCart() {
      cartItems += 1;
      document.getElementById('cart-count').innerText = cartItems.toString();
    }

    function submitOrder() {
      const card = document.getElementById('card').value.trim();
      const name = document.getElementById('name').value.trim();
      const successDiv = document.getElementById('confirmation-alert');
      const errorDiv = document.getElementById('error-alert');

      if (card.includes('0000') || card.toLowerCase().includes('fail') || !name) {
        successDiv.style.display = 'none';
        errorDiv.style.display = 'block';
      } else {
        errorDiv.style.display = 'none';
        successDiv.style.display = 'block';
      }
    }
  </script>
</body>
</html>
"""


@router.get("/demo/storefront", response_class=HTMLResponse, summary="Safe local demonstration e-commerce storefront")
def get_demo_storefront() -> HTMLResponse:
    """Returns the isolated demonstration web application for Playwright end-to-end testing."""
    return HTMLResponse(content=DEMO_HTML, status_code=200)
