<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Client Details</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <div class="container">
        <img src="{{ url_for('static', filename='logo.png') }}" alt="Logo" class="logo">
        <a href="{{ url_for('client_list') }}" class="back-link">The Renewable Energy Experts</a>

        <h1>Client Details</h1>
        <table class="client-details">
            <tr><th>Name</th><td>{{ client.Client_Name }}</td></tr>
            <tr><th>Town</th><td>{{ client.Town }}</td></tr>
            <tr><th>City</th><td>{{ client.City }}</td></tr>
            <tr><th>Phone Number</th><td>{{ client.Phone_Number or '' }}</td></tr>
            <tr><th>Contact Person</th><td>{{ client.Contact_Person or '' }}</td></tr>
            <tr><th>Email Address</th><td>{{ client.email_address or '' }}</td></tr>
            <tr><th>Installation Date</th><td>{{ installation_date }}</td></tr>
        </table>

        <h2>Component Details</h2>

        <!-- Inverters -->
        {% if inverter_quantities %}
        <h3>Inverters</h3>
        <table class="component-details">
            <thead>
                <tr>
                    <th>Item Description</th>
                    <th>Inverter ID</th>
                    <th>Number of Solar Panels</th>
                </tr>
            </thead>
            <tbody>
                {% for item in inverter_quantities %}
                <tr>
                    <td>{% if item.total_quantity < 1 %}<s>{{ item.Item_Description }}</s>{% else %}{{ item.Item_Description }}{% endif %}</td>
                    <td>{{ item.Inverter_ID }}</td>
                    <td>{{ item.Number_of_Solar_Panels or '' }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% endif %}

        <!-- Batteries -->
        {% if battery_quantities %}
        <h3>Batteries</h3>
        <table class="component-details">
            <thead>
                <tr><th>Item Description</th><th>Total Quantity</th></tr>
            </thead>
            <tbody>
                {% for item in battery_quantities %}
                <tr><td>{{ item.Item_Description }}</td><td>{{ item.total_quantity }}</td></tr>
                {% endfor %}
            </tbody>
        </table>
        {% endif %}

        <!-- Victron Charge Controllers -->
        {% if victron_charge_controller_quantities %}
        <h3>Victron Charge Controllers</h3>
        <table class="component-details">
            <thead>
                <tr>
                    <th>Item Description</th>
                    <th>Controller ID</th>
                    <th>Number of Solar Panels</th>
                </tr>
            </thead>
            <tbody>
                {% for item in victron_charge_controller_quantities %}
                <tr>
                    <td>{% if item.total_quantity < 1 %}<s>{{ item.Item_Description }}</s>{% else %}{{ item.Item_Description }}{% endif %}</td>
                    <td>{{ item.Controller_ID }}</td>
                    <td>{{ item.Number_of_Solar_Panels or '' }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% endif %}
    </div>
</body>
</html>
