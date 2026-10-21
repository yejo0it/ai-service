/**
 * 새 여행 만들기: 여행지 순서를 숙소·항공 일정에 맞춘다.
 *
 * 여행지(Step 1)를 '홍콩 → 마카오'로 적었어도 숙소가 마카오 → 홍콩 순서의 숙박 기간이고 항공도 마카오로 입국했다면,
 * 실제 이동 순서인 '마카오 → 홍콩'으로 바꿔 저장한다.
 *
 * 규칙 (우선순위: 숙소 > 항공)
 * 1. 숙소가 있는 여행지는 체크인이 이른 순서로 놓는다. 숙소가 없는 여행지의 자리는 그대로 둔다.
 * 2. 항공: 입국 공항의 도시가 숙소가 없는 여행지면 맨 앞에, 출국 공항의 도시가 숙소가 없는 여행지면 맨 뒤에 둔다.
 *    입국·출국 도시에 숙소가 있으면 숙소 순서를 따른다(항공과 숙소가 어긋나도 숙박 기간이 더 구체적이라고 본다).
 * 3. 같은 도시를 두 번 방문하는 일정(도시가 중복)이거나 도시 이름을 맞출 수 없으면 순서를 바꾸지 않는다.
 */

interface OrderDestination {
  city: string;
  city_code: string;
}

interface OrderHotel {
  /** 숙소가 있는 여행지의 이름(Step 1의 도시명) */
  city: string;
  place_id: string;
  check_in: string;
  check_out: string;
}

export interface DestinationOrder<T extends OrderDestination> {
  destinations: T[];
  /** 순서가 바뀌었는지 */
  changed: boolean;
  /** 바뀌기 전·후의 도시 이름 (안내 문구용) */
  before: string[];
  after: string[];
}

const nameOf = (destination: OrderDestination) => destination.city.trim();

export function orderDestinations<T extends OrderDestination>(
  destinations: T[],
  hotels: OrderHotel[],
  arrivalCity?: string,
  departureCity?: string,
): DestinationOrder<T> {
  const before = destinations.map(nameOf);
  const unchanged: DestinationOrder<T> = { destinations, changed: false, before, after: before };
  if (destinations.length < 2 || before.some((name) => !name) || new Set(before).size !== before.length) return unchanged;

  // 1) 숙소가 있는 여행지: 체크인이 이른 순서(같으면 체크아웃 순)
  const stays = hotels
    .filter((hotel) => hotel.place_id && hotel.check_in && before.includes(hotel.city.trim()))
    .sort((a, b) => a.check_in.localeCompare(b.check_in) || (a.check_out || "").localeCompare(b.check_out || ""));
  const hotelCities = [...new Set(stays.map((hotel) => hotel.city.trim()))];

  const order = [...before];
  if (hotelCities.length >= 2) {
    // 숙소가 있는 여행지가 차지한 자리에, 숙소 순서대로 다시 채운다(숙소가 없는 여행지는 제자리).
    const slots = order.flatMap((name, index) => (hotelCities.includes(name) ? [index] : []));
    slots.forEach((slot, position) => {
      order[slot] = hotelCities[position];
    });
  }

  // 2) 항공: 숙소가 없는 입국 도시는 맨 앞, 출국 도시는 맨 뒤
  const arrival = arrivalCity?.trim();
  const departure = departureCity?.trim();
  if (arrival && order.includes(arrival) && !hotelCities.includes(arrival)) {
    order.splice(order.indexOf(arrival), 1);
    order.unshift(arrival);
  }
  if (departure && departure !== arrival && order.includes(departure) && !hotelCities.includes(departure)) {
    order.splice(order.indexOf(departure), 1);
    order.push(departure);
  }
  // 입국 도시가 숙소 없이 앞으로 갔는데 출국 도시가 이미 맨 앞이던 경우 등으로 규칙이 서로 부딪히면 입국을 우선한다.
  const changed = order.some((name, index) => name !== before[index]);
  if (!changed) return unchanged;

  const byName = new Map(destinations.map((destination) => [nameOf(destination), destination]));
  return { destinations: order.map((name) => byName.get(name) as T), changed: true, before, after: order };
}
