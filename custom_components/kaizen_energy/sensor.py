# Copyright (C) 2021-2023 Gorka Olalde Mendia
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.
"""Sensor platform for Kaizen Energy integration."""

from datetime import datetime, timedelta
import itertools

from homeassistant_historical_sensor import (
    HistoricalSensor,
    HistoricalState,
    PollUpdateMixin,
)

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import TridensApiClient
from .const import DOMAIN

PLATFORM = "sensor"


class KaizenEnergySensor(PollUpdateMixin, HistoricalSensor, SensorEntity):
    """Kaizen Energy sensor for historical consumption data.

    Base classes:
    - SensorEntity: This is a sensor
    - HistoricalSensor: This sensor implements historical sensor methods
    - PollUpdateMixin: Historical sensors disable poll, this mixing
                       reenables poll only for historical states and not for
                       present state
    """

    # Update historical data once per day
    UPDATE_INTERVAL = timedelta(days=1)

    def __init__(
        self,
        config_entry: ConfigEntry,
        device_info: DeviceInfo,
        api: TridensApiClient,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()

        self.config_entry = config_entry
        self.api = api

        self._attr_has_entity_name = True
        self._attr_name = "Energy Consumption"  # Use device name

        # Create unique_id based on config entry and username
        username = config_entry.data.get("username", "unknown")
        self._attr_unique_id = f"{config_entry.entry_id}_{username}_energy"

        self._attr_device_info = device_info
        self._attr_entity_registry_enabled_default = True
        self._attr_state = None

        # Define whatever you are
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY

        # We DON'T opt-in for statistics (don't set state_class). Why?
        #
        # Those statistics are generated from a real sensor, this sensor, but we don't
        # want that hass try to do anything with those statistics because we
        # (HistoricalSensor) handle generation and importing
        #
        # self._attr_state_class = SensorStateClass.MEASUREMENT

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

    async def async_update_historical(self):
        """Fill historical states with consumption data.

        This function is equivalent to the `Sensor.async_update` from
        HomeAssistant core.

        Important: You must provide datetime with tzinfo.
        Note: API readings are dated at 1:00 AM but represent the previous day.
        """
        hist_states = []
        consumption_records = await self.api.fetch_consumption(
            start=datetime.now() - timedelta(days=15), end=datetime.now()
        )
        for consumption_record in consumption_records:
            dt = consumption_record.time_of_read.astimezone()
            # Readings at 1:00 AM represent the previous day's consumption
            # Subtract 1 day to assign to the correct date
            corrected_dt = dt - timedelta(days=1)
            state = consumption_record.consumption
            hist_states.append(
                HistoricalState(
                    state=state,
                    dt=dt_util.as_local(
                        corrected_dt
                    ),  # Add tzinfo, required by HistoricalSensor
                )
            )
        self._attr_historical_states = hist_states

    @property
    def statistic_id(self) -> str:
        """Return the statistic ID."""
        return self.entity_id

    def get_statistic_metadata(self) -> StatisticMetaData:
        """Return statistic metadata.

        Add sum and mean_type to base statistics metadata.
        Important: HistoricalSensor.get_statistic_metadata returns an
        internal source by default.

        Each data point represents a full day's consumption.
        """
        meta = super().get_statistic_metadata()
        meta["has_sum"] = True
        meta["mean_type"] = StatisticMeanType.NONE  # No mean for daily totals
        meta["unit_of_measurement"] = UnitOfEnergy.KILO_WATT_HOUR
        meta["unit_class"] = "energy"  # Specifies energy unit conversion class

        return meta

    async def async_calculate_statistic_data(
        self, hist_states: list[HistoricalState], *, latest: dict | None = None
    ) -> list[StatisticData]:
        """Calculate statistics data from historical states.

        Each historical state represents a full day's consumption.
        We group by day and accumulate the total consumption.
        """
        accumulated = latest["sum"] if latest else 0

        def day_block_for_hist_state(hist_state: HistoricalState) -> datetime:
            """Determine which day block a historical state belongs to."""
            # Normalize to start of day (midnight)
            return hist_state.dt.replace(hour=0, minute=0, second=0, microsecond=0)

        ret = []
        for dt, collection_it in itertools.groupby(
            hist_states, key=day_block_for_hist_state
        ):
            collection = list(collection_it)
            # Each record is already a daily total, so we sum if there are multiple
            # readings for the same day (shouldn't happen normally)
            daily_total = sum(x.state for x in collection)
            accumulated = accumulated + daily_total

            ret.append(
                StatisticData(
                    start=dt,
                    state=daily_total,
                    sum=accumulated,
                )
            )

        return ret


class KaizenEnergyCostSensor(PollUpdateMixin, HistoricalSensor, SensorEntity):
    """Kaizen Energy cost sensor for historical cost data.

    Base classes:
    - SensorEntity: This is a sensor
    - HistoricalSensor: This sensor implements historical sensor methods
    - PollUpdateMixin: Historical sensors disable poll, this mixing
                       reenables poll only for historical states and not for
                       present state
    """

    # Update historical data once per day
    UPDATE_INTERVAL = timedelta(days=1)

    def __init__(
        self,
        config_entry: ConfigEntry,
        device_info: DeviceInfo,
        api: TridensApiClient,
    ) -> None:
        """Initialize the sensor."""
        super().__init__()

        self.config_entry = config_entry
        self.api = api

        self._attr_has_entity_name = True
        self._attr_name = "Cost"

        # Create unique_id based on config entry and customer ID
        username = config_entry.data.get("username", "unknown")
        self._attr_unique_id = f"{config_entry.entry_id}_{username}_cost"

        self._attr_device_info = device_info
        self._attr_entity_registry_enabled_default = True
        self._attr_state = None

        # Define as monetary sensor
        self._attr_native_unit_of_measurement = CURRENCY_EURO
        self._attr_device_class = SensorDeviceClass.MONETARY

        # We DON'T opt-in for statistics (don't set state_class). Why?
        #
        # Those statistics are generated from a real sensor, this sensor, but we don't
        # want that hass try to do anything with those statistics because we
        # (HistoricalSensor) handle generation and importing
        #
        # self._attr_state_class = SensorStateClass.MEASUREMENT

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

    async def async_update_historical(self):
        """Fill historical states with cost data.

        This function is equivalent to the `Sensor.async_update` from
        HomeAssistant core.

        Important: You must provide datetime with tzinfo.
        Note: API readings are dated at 1:00 AM but represent the previous day.
        """
        hist_states = []
        consumption_records = await self.api.fetch_consumption(
            start=datetime.now() - timedelta(days=30), end=datetime.now()
        )
        for consumption_record in consumption_records:
            dt = consumption_record.time_of_read.astimezone()
            # Readings at 1:00 AM represent the previous day's cost
            # Subtract 1 day to assign to the correct date
            corrected_dt = dt - timedelta(days=1)
            state = consumption_record.cost  # Use cost field instead of consumption
            hist_states.append(
                HistoricalState(
                    state=state,
                    dt=dt_util.as_local(
                        corrected_dt
                    ),  # Add tzinfo, required by HistoricalSensor
                )
            )
        self._attr_historical_states = hist_states

    @property
    def statistic_id(self) -> str:
        """Return the statistic ID."""
        return self.entity_id

    def get_statistic_metadata(self) -> StatisticMetaData:
        """Return statistic metadata.

        Add sum and mean_type to base statistics metadata.
        Important: HistoricalSensor.get_statistic_metadata returns an
        internal source by default.

        Each data point represents a full day's cost.
        """
        meta = super().get_statistic_metadata()
        meta["has_sum"] = True
        meta["mean_type"] = StatisticMeanType.NONE  # No mean for daily totals
        meta["unit_of_measurement"] = CURRENCY_EURO
        meta["unit_class"] = None  # No unit conversion for currency

        return meta

    async def async_calculate_statistic_data(
        self, hist_states: list[HistoricalState], *, latest: dict | None = None
    ) -> list[StatisticData]:
        """Calculate statistics data from historical states.

        Each historical state represents a full day's cost.
        We group by day and accumulate the total cost.
        """
        accumulated = latest["sum"] if latest else 0

        def day_block_for_hist_state(hist_state: HistoricalState) -> datetime:
            """Determine which day block a historical state belongs to."""
            # Normalize to start of day (midnight)
            return hist_state.dt.replace(hour=0, minute=0, second=0, microsecond=0)

        ret = []
        for dt, collection_it in itertools.groupby(
            hist_states, key=day_block_for_hist_state
        ):
            collection = list(collection_it)
            # Each record is already a daily total, so we sum if there are multiple
            # readings for the same day (shouldn't happen normally)
            daily_total = sum(x.state for x in collection)
            accumulated = accumulated + daily_total

            ret.append(
                StatisticData(
                    start=dt,
                    state=daily_total,
                    sum=accumulated,
                )
            )

        return ret


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kaizen Energy sensor from a config entry."""
    device_info = hass.data[DOMAIN][config_entry.entry_id]
    username = config_entry.data.get("username")
    password = config_entry.data.get("password")

    if not (username and password):
        raise ValueError("Missing configuration data")

    session = async_get_clientsession(hass)
    tridens_api = TridensApiClient(username, password, session)

    sensors = [
        KaizenEnergySensor(
            config_entry=config_entry,
            device_info=device_info,
            api=tridens_api,
        ),
        KaizenEnergyCostSensor(
            config_entry=config_entry,
            device_info=device_info,
            api=tridens_api,
        ),
    ]
    async_add_entities(sensors)
