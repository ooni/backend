<!DOCTYPE html>
<html lang="en">
  <style>
    div.form label {
      width: 20em;
    }
  </style>
  <form action="/chart" method="get">
    <div class="form">
      <label for="name">CC: </label>
      <input type="text" name="ccs" required>
    </div>
    <div class="form">
      <label for="name">test name: </label>
      <input type="text" name="test_names" value="web_connectivity" required>
    </div>
    <div class="form">
      <label for="name">Input: </label>
      <input type="text" name="inputs">
    </div>
    <div class="form">
      <label for="name">start date: </label>
      <input type="text" name="start_date">
    </div>
    <input type="submit" />
  </form>
</html>
