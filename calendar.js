const FIXED_ROMAN_DAYS = {
  "01-01": ["The Circumcision of Our Lord", "White"],
  "01-06": ["The Epiphany of Our Lord", "White"],
  "01-18": ["Chair of Saint Peter at Rome", "White"],
  "01-21": ["Saint Agnes, Virgin and Martyr", "Red"],
  "01-25": ["Conversion of Saint Paul", "White"],
  "01-28": ["Saint Peter Nolasco, Confessor", "White"],
  "01-31": ["Saint John Bosco, Confessor", "White"],
  "02-02": ["Purification of the Blessed Virgin Mary", "White"],
  "02-11": ["Our Lady of Lourdes", "White"],
  "02-22": ["Chair of Saint Peter at Antioch", "White"],
  "02-24": ["Saint Matthias, Apostle", "Red"],
  "03-07": ["Saint Thomas Aquinas, Confessor and Doctor", "White"],
  "03-19": ["Saint Joseph, Spouse of the Blessed Virgin Mary", "White"],
  "03-25": ["The Annunciation of the Blessed Virgin Mary", "White"],
  "04-25": ["Saint Mark, Evangelist", "Red"],
  "05-01": ["Saint Joseph the Worker", "White"],
  "05-31": ["Queenship of the Blessed Virgin Mary", "White"],
  "06-13": ["Saint Anthony of Padua, Confessor and Doctor", "White"],
  "06-24": ["Nativity of Saint John the Baptist", "White"],
  "06-29": ["Saints Peter and Paul, Apostles", "Red"],
  "07-01": ["The Most Precious Blood of Our Lord Jesus Christ", "Red"],
  "07-02": ["Visitation of the Blessed Virgin Mary", "White"],
  "07-22": ["Saint Mary Magdalene, Penitent", "White"],
  "07-25": ["Saint James, Apostle", "Red"],
  "07-26": ["Saint Anne, Mother of the Blessed Virgin Mary", "White"],
  "08-06": ["The Transfiguration of Our Lord", "White"],
  "08-10": ["Saint Lawrence, Deacon and Martyr", "Red"],
  "08-15": ["Assumption of the Blessed Virgin Mary", "White"],
  "08-22": ["Immaculate Heart of the Blessed Virgin Mary", "White"],
  "08-24": ["Saint Bartholomew, Apostle", "Red"],
  "09-08": ["Nativity of the Blessed Virgin Mary", "White"],
  "09-14": ["Exaltation of the Holy Cross", "Red"],
  "09-21": ["Saint Matthew, Apostle and Evangelist", "Red"],
  "09-29": ["Dedication of Saint Michael the Archangel", "White"],
  "10-02": ["The Holy Guardian Angels", "White"],
  "10-07": ["Our Lady of the Most Holy Rosary", "White"],
  "10-18": ["Saint Luke, Evangelist", "Red"],
  "10-28": ["Saints Simon and Jude, Apostles", "Red"],
  "11-01": ["All Saints", "White"],
  "11-02": ["Commemoration of All the Faithful Departed", "Black or Violet"],
  "11-30": ["Saint Andrew, Apostle", "Red"],
  "12-08": ["Immaculate Conception of the Blessed Virgin Mary", "White"],
  "12-21": ["Saint Thomas, Apostle", "Red"],
  "12-25": ["Nativity of Our Lord", "White"],
  "12-26": ["Saint Stephen, First Martyr", "Red"],
  "12-27": ["Saint John, Apostle and Evangelist", "White"],
  "12-28": ["The Holy Innocents, Martyrs", "Red"]
};

function romanCalendarToday(date = new Date()) {
  const key = `${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  const fixed = FIXED_ROMAN_DAYS[key];
  const sunday = date.getDay() === 0;
  return {
    date: new Intl.DateTimeFormat('en', {weekday:'long', day:'numeric', month:'long'}).format(date),
    title: fixed?.[0] || (sunday ? 'Sunday in the Roman Calendar' : 'Feria'),
    colour: fixed?.[1] || (sunday ? 'According to the season' : 'According to the season')
  };
}
