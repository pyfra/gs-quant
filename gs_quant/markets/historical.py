"""
Copyright 2019 Goldman Sachs.
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
"""
import datetime as dt
from concurrent.futures import Future
import pandas as pd
from typing import Iterable, Optional, Tuple, Union

from gs_quant.base import Priceable
from gs_quant.datetime.date import business_day_offset, date_range
from gs_quant.target.risk import PricingDateAndMarketDataAsOf, RiskMeasure
from .core import PricingCache, PricingContext


class HistoricalPricingContext(PricingContext):

    """
    A context for producing valuations over multiple dates
    """

    def __init__(
            self,
            start: Optional[Union[int, dt.date]] = None,
            end: Optional[Union[int, dt.date]] = None,
            calendars: Union[str, Tuple] = (),
            dates: Optional[Iterable[dt.date]] = None,
            is_async: bool = False,
            is_batch: bool = False,
            use_cache: bool = False
    ):
        """
        A context for producing valuations over multiple dates

        :param start: start date
        :param end: end date (defaults to today)
        :param calendars: holiday calendars
        :param dates: a custom iterable of dates
        :param is_async: return immediately (True) or wait for results (False). Defaults to False
        :param is_batch: use for calculations expected to run longer than 3 mins, to avoid timeouts.
        It can be used with is_async=True|False
        :param use_cache: store results in the pricing cache

        **Examples**

        >>> from gs_quant.instrument import IRSwap
        >>>
        >>> ir_swap = IRSwap('Pay', '10y', 'DKK')
        >>> with HistoricalPricingContext(10):
        >>>     price_f = ir_swap.price()
        >>>
        >>> price_series = price_f.result()
        """
        super().__init__(is_async=is_async, is_batch=is_batch, use_cache=use_cache)
        self.__calc_dates = None

        if start is not None:
            if dates is not None:
                raise ValueError('Must supply start or dates, not both')

            if end is None:
                end = dt.date.today()

            self.__date_range = tuple(date_range(start, end, calendars=calendars))
        elif dates is not None:
            self.__date_range = tuple(dates)
        else:
            raise ValueError('Must supply start or dates')

    def _on_exit(self, exc_type, exc_val, exc_tb):
        try:
            super()._on_exit(exc_type, exc_val, exc_tb)
        finally:
            self.__calc_dates = None

    def resolve_fields(self, priceable: Priceable, in_place: bool) -> Optional[Union[Priceable, Future]]:
        if in_place:
            raise RuntimeError('Cannot resolve in place under a HistoricalPricingContext')

        return super().resolve_fields(priceable, in_place)

    @property
    def pricing_date(self):
        return self.__date_range

    @property
    def _pricing_market_data_as_of(self) -> Tuple[PricingDateAndMarketDataAsOf, ...]:
        return tuple(
            PricingDateAndMarketDataAsOf(
                d, business_day_offset(d, -1, roll='preceding') if d == dt.date.today() else d)
            for d in (self.__calc_dates if self.__calc_dates is not None else self.__date_range))

    def calc(self, priceable: Priceable, risk_measure: Union[RiskMeasure, Iterable[RiskMeasure]])\
            -> Union[pd.DataFrame, pd.Series, Future]:
        if self.use_cache:
            cached_dates = PricingCache.dates(priceable, self.market_data_location, risk_measure) or ()
            calc_dates = set(self.__date_range).difference(cached_dates)
            self.__calc_dates = calc_dates if self.__calc_dates is None else self.__calc_dates | calc_dates

        return super().calc(priceable, risk_measure)
