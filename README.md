# Kaizen Energy Integration for Home Assistant

[![Open Integration](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=olaldiko&repository=homeassistant-kaizen-energy&category=integration)

This integration allows to retrieve consumption and cost data from the Kaizen Energy utility provider.

It uses the [Tridens Monetization API](https://tridenstechnology.com/monetization-api-docs/) under the hood, so it could be easily adapt to other providers by changing the `TRIDENS_SITE` constant. Unfortunately, I don't have access to other provider APIs to confirm this.

The integration reports both the consumed energy (in KWh) and the cost (in Eur).

## Sensors

- **Energy Consumption** Consumed daily heating energy in KWh.
- **Cost** Reported cost for each day

## Data retrieval

The integration uses the [Tridens Monetization API](https://tridenstechnology.com/monetization-api-docs/).

- Authenticate against the API with username/password on the `https://app.tridenstechnology.com/monetization/authenticate` POST endpoint [Docs](https://tridenstechnology.com/monetization-api-docs/)
- Obtain the `customer_id` from the JWT token
- Retrieve the consumptions throught the `https://app.tridenstechnology.com/monetization/api/v1/customers{customer_id}/usage-events` GET endpoint. (Undocumented)

## Schedule

Daily retrieval of values.

## Acknowledgements

- [Home-Assistant-Electric-Ireland](https://github.com/barreeeiroo/Home-Assistant-Electric-Ireland): For the inspiration for this integration and referenced historical sensors integration.
- [Historical sensors for Home Assistant](https://github.com/ldotlopez/ha-historical-sensor): provided the library and
  skeleton to create the bare minimum working version.
