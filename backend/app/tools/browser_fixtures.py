"""Operator-owned fixtures. No user URLs, scripts, credentials, or real bookings."""

ORIGIN = "https://booking-fixture.test"
PAGE_URL = f"{ORIGIN}/booking"
API_URL = f"{ORIGIN}/api/bookings"

BOOKING_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Synthetic booking</title>
<link rel="icon" href="data:,"></head><body>
<h1>Synthetic booking</h1>
<form id="booking-form">
  <label for="customer">Customer name</label>
  <input id="customer" name="customer" required>
  <button type="submit">Book appointment</button>
</form>
<p role="status" id="result"></p>
<script>
document.getElementById('booking-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const result = document.getElementById('result');
  try {
    const response = await fetch('/api/bookings', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({customer: document.getElementById('customer').value})
    });
    const data = await response.json();
    if (!response.ok) {
      console.error('Synthetic booking API rejected the request');
      result.textContent = 'Booking unavailable';
    } else if (data.confirmed === true) {
      result.textContent = 'Booking confirmed';
    } else {
      result.textContent = 'Confirmation missing';
    }
  } catch (error) {
    console.error('Synthetic booking request failed');
    result.textContent = 'Booking unavailable';
  }
});
</script></body></html>
"""
