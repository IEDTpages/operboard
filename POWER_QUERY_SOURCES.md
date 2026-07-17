# Power Query, извлечённые из PBIX

## TTF

```powerquery
let
  Источник = Web.BrowserContents("https://www.profinance.ru/charts/ttfusd1000/lc91h"),
  #"Извлеченная таблица из HTML" = Html.Table(Источник, {{"Column0", "TABLE[id='table_history'] > * > TR > :nth-child(1)"}, {"Column1", "TABLE[id='table_history'] > * > TR > :nth-child(2)"}, {"Column2", "TABLE[id='table_history'] > * > TR > :nth-child(3)"}, {"Column3", "TABLE[id='table_history'] > * > TR > :nth-child(4)"}, {"Column4", "TABLE[id='table_history'] > * > TR > :nth-child(5)"}}, [RowSelector = "TABLE[id='table_history'] > * > TR"]),
  #"Повышенные заголовки" = Table.PromoteHeaders(#"Извлеченная таблица из HTML", [PromoteAllScalars = true]),
    #"Измененный тип" = Table.TransformColumnTypes(#"Повышенные заголовки",{{"Время", type date}}),
    #"Удаленные столбцы" = Table.RemoveColumns(#"Измененный тип",{"Open", "High", "Low"}),
    #"Переименованные столбцы" = Table.RenameColumns(#"Удаленные столбцы",{{"Close", "Газ"}}),
    #"Замененное значение" = Table.ReplaceValue(#"Переименованные столбцы",".",",",Replacer.ReplaceText,{"Газ"}),
    #"Переименованные столбцы1" = Table.RenameColumns(#"Замененное значение",{{"Время", "Дата"}}),
    #"Измененный тип1" = Table.TransformColumnTypes(#"Переименованные столбцы1",{{"Газ", type number}})
in
    #"Измененный тип1"
```

## I GOT THE KEYS

```powerquery
let
  Источник = Web.BrowserContents("https://www.cbr.ru/hd_base/keyrate/?UniDbQuery.Posted=True&UniDbQuery.From=01.01.2021&UniDbQuery.To=12.12.2030"),
  #"Извлеченная таблица из HTML" = Html.Table(Источник, {{"Column0", "TABLE.data > * > TR > :nth-child(1)"}, {"Column1", "TABLE.data > * > TR > :nth-child(2)"}}, [RowSelector = "TABLE.data > * > TR"]),
  #"Повышенные заголовки" = Table.PromoteHeaders(#"Извлеченная таблица из HTML", [PromoteAllScalars = true]),
  #"Измененный тип столбца" = Table.TransformColumnTypes(#"Повышенные заголовки", {{"Дата", type date}, {"Ставка", type number}}, "ru"),
    #"Переименованные столбцы" = Table.RenameColumns(#"Измененный тип столбца",{{"Дата", "Дата"}, {"Ставка", "Ключ"}}),
    #"Измененный тип" = Table.TransformColumnTypes(#"Переименованные столбцы",{{"Ключ", type number}})
in
    #"Измененный тип"
```

## CIF ARA

```powerquery
let
  Источник = Web.BrowserContents("https://www.profinance.ru/charts/coaleu/lc91h"),
  #"Извлеченная таблица из HTML" = Html.Table(Источник, {{"Column0", "TABLE[id='table_history'] > * > TR > :nth-child(1)"}, {"Column1", "TABLE[id='table_history'] > * > TR > :nth-child(2)"}, {"Column2", "TABLE[id='table_history'] > * > TR > :nth-child(3)"}, {"Column3", "TABLE[id='table_history'] > * > TR > :nth-child(4)"}, {"Column4", "TABLE[id='table_history'] > * > TR > :nth-child(5)"}}, [RowSelector = "TABLE[id='table_history'] > * > TR"]),
  #"Повышенные заголовки" = Table.PromoteHeaders(#"Извлеченная таблица из HTML", [PromoteAllScalars = true]),
  #"Измененный тип столбца" = Table.TransformColumnTypes(#"Повышенные заголовки", {{"Время", type date}}, "ru"),
    #"Удаленные столбцы" = Table.RemoveColumns(#"Измененный тип столбца",{"Open", "High", "Low"}),
    #"Переименованные столбцы" = Table.RenameColumns(#"Удаленные столбцы",{{"Close", "ARA"}, {"Время", "Дата"}}),
    #"Замененное значение" = Table.ReplaceValue(#"Переименованные столбцы",".",",",Replacer.ReplaceText,{"ARA"}),
    #"Измененный тип" = Table.TransformColumnTypes(#"Замененное значение",{{"ARA", type number}})
in
  #"Измененный тип"
```

## LME

```powerquery
let
  Источник = Web.BrowserContents("https://www.profinance.ru/charts/aluminum/lc91h"),
  #"Извлеченная таблица из HTML" = Html.Table(Источник, {{"Column0", "TABLE[id='table_history'] > * > TR > :nth-child(1)"}, {"Column1", "TABLE[id='table_history'] > * > TR > :nth-child(2)"}, {"Column2", "TABLE[id='table_history'] > * > TR > :nth-child(3)"}, {"Column3", "TABLE[id='table_history'] > * > TR > :nth-child(4)"}, {"Column4", "TABLE[id='table_history'] > * > TR > :nth-child(5)"}}, [RowSelector = "TABLE[id='table_history'] > * > TR"]),
  #"Повышенные заголовки" = Table.PromoteHeaders(#"Извлеченная таблица из HTML", [PromoteAllScalars = true]),
  #"Измененный тип столбца" = Table.TransformColumnTypes(#"Повышенные заголовки", {{"Время", type date}}, "ru"),
    #"Замененное значение" = Table.ReplaceValue(#"Измененный тип столбца",".",",",Replacer.ReplaceText,{"Close"}),
    #"Измененный тип" = Table.TransformColumnTypes(#"Замененное значение",{{"Close", type number}}),
    #"Удаленные столбцы" = Table.RemoveColumns(#"Измененный тип",{"Open", "High", "Low"}),
    #"Переименованные столбцы" = Table.RenameColumns(#"Удаленные столбцы",{{"Close", "Алюминий"}, {"Время", "Дата"}})
in
  #"Переименованные столбцы"
```

## Urals

```powerquery
let
  Источник = Web.BrowserContents("https://www.profinance.ru/charts/urals_med/lc91h"),
  #"Извлеченная таблица из HTML" = Html.Table(Источник, {{"Column0", "TABLE[id='table_history'] > * > TR > :nth-child(1)"}, {"Column1", "TABLE[id='table_history'] > * > TR > :nth-child(2)"}, {"Column2", "TABLE[id='table_history'] > * > TR > :nth-child(3)"}, {"Column3", "TABLE[id='table_history'] > * > TR > :nth-child(4)"}, {"Column4", "TABLE[id='table_history'] > * > TR > :nth-child(5)"}}, [RowSelector = "TABLE[id='table_history'] > * > TR"]),
  #"Повышенные заголовки" = Table.PromoteHeaders(#"Извлеченная таблица из HTML", [PromoteAllScalars = true]),
  #"Измененный тип столбца" = Table.TransformColumnTypes(#"Повышенные заголовки", {{"Время", type date}}, "ru"),
    #"Удаленные столбцы" = Table.RemoveColumns(#"Измененный тип столбца",{"Open", "High", "Low"}),
    #"Переименованные столбцы" = Table.RenameColumns(#"Удаленные столбцы",{{"Close", "Urals"}}),
    #"Замененное значение" = Table.ReplaceValue(#"Переименованные столбцы",".",",",Replacer.ReplaceText,{"Urals"}),
    #"Измененный тип" = Table.TransformColumnTypes(#"Замененное значение",{{"Urals", type number}}),
    #"Переименованные столбцы1" = Table.RenameColumns(#"Измененный тип",{{"Время", "Дата"}})
in
  #"Переименованные столбцы1"
```

## RUB/USD

```powerquery
let
  Источник = Xml.Tables(Web.Contents("https://www.cbr.ru/scripts/XML_dynamic.asp?date_req1=01/01/2021&date_req2=01/01/2031&VAL_NM_RQ=R01235")),
  #"Измененный тип столбца" = Table.TransformColumnTypes(Источник, {{"Attribute:ID", type text}, {"Attribute:DateRange1", type date}, {"Attribute:DateRange2", type date}, {"Attribute:name", type text}}, "ru"),
    Record = #"Измененный тип столбца"{0}[Record],
    #"Измененный тип" = Table.TransformColumnTypes(Record,{{"Nominal", Int64.Type}, {"Value", type number}, {"VunitRate", type number}, {"Attribute:Date", type date}, {"Attribute:Id", type text}}),
    #"Сортированные строки" = Table.Sort(#"Измененный тип",{{"Attribute:Date", Order.Descending}}),
    #"Удаленные столбцы" = Table.RemoveColumns(#"Сортированные строки",{"Nominal", "VunitRate"}),
    #"Переименованные столбцы" = Table.RenameColumns(#"Удаленные столбцы",{{"Value", "Курс"}, {"Attribute:Date", "Дата"}}),
    #"Удаленные столбцы1" = Table.RemoveColumns(#"Переименованные столбцы",{"Attribute:Id"})
in
  #"Удаленные столбцы1"
```

## Brent

```powerquery
let
  Источник = Web.BrowserContents("https://www.profinance.ru/charts/brent/lc91h"),
  #"Извлеченная таблица из HTML" = Html.Table(Источник, {{"Column0", "TABLE[id='table_history'] > * > TR > :nth-child(1)"}, {"Column1", "TABLE[id='table_history'] > * > TR > :nth-child(2)"}, {"Column2", "TABLE[id='table_history'] > * > TR > :nth-child(3)"}, {"Column3", "TABLE[id='table_history'] > * > TR > :nth-child(4)"}, {"Column4", "TABLE[id='table_history'] > * > TR > :nth-child(5)"}}, [RowSelector = "TABLE[id='table_history'] > * > TR"]),
  #"Повышенные заголовки" = Table.PromoteHeaders(#"Извлеченная таблица из HTML", [PromoteAllScalars = true]),
  #"Измененный тип столбца" = Table.TransformColumnTypes(#"Повышенные заголовки", {{"Время", type date}}, "ru"),
    #"Удаленные столбцы" = Table.RemoveColumns(#"Измененный тип столбца",{"Open", "High", "Low"}),
    #"Переименованные столбцы" = Table.RenameColumns(#"Удаленные столбцы",{{"Close", "Brent"}, {"Время", "Дата"}}),
    #"Замененное значение" = Table.ReplaceValue(#"Переименованные столбцы",".",",",Replacer.ReplaceText,{"Brent"}),
    #"Измененный тип" = Table.TransformColumnTypes(#"Замененное значение",{{"Brent", type number}})
in
  #"Измененный тип"
```

## WHFOB

```powerquery
let
   source = List.Numbers(1, 14, 100),
   to_table = Table.FromList(
      source,
      Splitter.SplitByNothing(),
      null,
      null,
      ExtraValues.Error
   ),
   table_add_col = Table.AddColumn(
      to_table,
      "Пользовательская",
      each Xml.Tables(
         Web.Contents(
            "http://iss.moex.com/iss/history/engines/stock/markets/index/securities/WHFOB.xml?start="
               & Text.From([Column1])
         )
      ){0}[Table]{0}[rows]{0}[row]
   ),
   cols_select = Table.SelectColumns(table_add_col, {"Пользовательская"}),
   col_expand_table = Table.ExpandTableColumn(
      cols_select,
      "Пользовательская",
      {
         "Attribute:BOARDID",
         "Attribute:TRADEDATE",
         "Attribute:SHORTNAME",
         "Attribute:SECID",
         "Attribute:NUMTRADES",
         "Attribute:VALUE",
         "Attribute:OPEN",
         "Attribute:LOW",
         "Attribute:HIGH",
         "Attribute:LEGALCLOSEPRICE",
         "Attribute:WAPRICE",
         "Attribute:CLOSE",
         "Attribute:VOLUME",
         "Attribute:MARKETPRICE2",
         "Attribute:MARKETPRICE3",
         "Attribute:ADMITTEDQUOTE",
         "Attribute:MP2VALTRD",
         "Attribute:MARKETPRICE3TRADESVALUE",
         "Attribute:ADMITTEDVALUE",
         "Attribute:WAVAL"
      },
      {
         "Attribute:BOARDID",
         "Attribute:TRADEDATE",
         "Attribute:SHORTNAME",
         "Attribute:SECID",
         "Attribute:NUMTRADES",
         "Attribute:VALUE",
         "Attribute:OPEN",
         "Attribute:LOW",
         "Attribute:HIGH",
         "Attribute:LEGALCLOSEPRICE",
         "Attribute:WAPRICE",
         "Attribute:CLOSE",
         "Attribute:VOLUME",
         "Attribute:MARKETPRICE2",
         "Attribute:MARKETPRICE3",
         "Attribute:ADMITTEDQUOTE",
         "Attribute:MP2VALTRD",
         "Attribute:MARKETPRICE3TRADESVALUE",
         "Attribute:ADMITTEDVALUE",
         "Attribute:WAVAL"
      }
   ),
   types = Table.TransformColumnNames(
      col_expand_table,
      each Text.AfterDelimiter(_, ":")
   ),
    #"Удаленные столбцы" = Table.RemoveColumns(types,{"VOLUME", "MARKETPRICE2", "MARKETPRICE3", "ADMITTEDQUOTE", "MP2VALTRD", "MARKETPRICE3TRADESVALUE", "ADMITTEDVALUE", "WAVAL", "BOARDID", "SHORTNAME", "SECID", "NUMTRADES", "VALUE", "OPEN", "LOW", "HIGH", "LEGALCLOSEPRICE", "WAPRICE"}),
    #"Измененный тип" = Table.TransformColumnTypes(#"Удаленные столбцы",{{"TRADEDATE", type date}}),
    #"Переименованные столбцы" = Table.RenameColumns(#"Измененный тип",{{"TRADEDATE", "Дата"}}),
    #"Замененное значение" = Table.ReplaceValue(#"Переименованные столбцы",".",",",Replacer.ReplaceText,{"CLOSE"}),
    #"Измененный тип1" = Table.TransformColumnTypes(#"Замененное значение",{{"CLOSE", type number}}),
    #"Переименованные столбцы1" = Table.RenameColumns(#"Измененный тип1",{{"CLOSE", "Пшеница"}}),
    #"Сортированные строки" = Table.Sort(#"Переименованные столбцы1",{{"Дата", Order.Descending}})
in
    #"Сортированные строки"
```

## SOEXP

```powerquery
let
   source = List.Numbers(1, 11, 100),
   to_table = Table.FromList(
      source,
      Splitter.SplitByNothing(),
      null,
      null,
      ExtraValues.Error
   ),
   table_add_col = Table.AddColumn(
      to_table,
      "Пользовательская",
      each Xml.Tables(
         Web.Contents(
            "http://iss.moex.com/iss/history/engines/stock/markets/index/securities/SOEXP.xml?start="
               & Text.From([Column1])
         )
      ){0}[Table]{0}[rows]{0}[row]
   ),
   cols_select = Table.SelectColumns(table_add_col, {"Пользовательская"}),
   col_expand_table = Table.ExpandTableColumn(
      cols_select,
      "Пользовательская",
      {
         "Attribute:BOARDID",
         "Attribute:TRADEDATE",
         "Attribute:SHORTNAME",
         "Attribute:SECID",
         "Attribute:NUMTRADES",
         "Attribute:VALUE",
         "Attribute:OPEN",
         "Attribute:LOW",
         "Attribute:HIGH",
         "Attribute:LEGALCLOSEPRICE",
         "Attribute:WAPRICE",
         "Attribute:CLOSE",
         "Attribute:VOLUME",
         "Attribute:MARKETPRICE2",
         "Attribute:MARKETPRICE3",
         "Attribute:ADMITTEDQUOTE",
         "Attribute:MP2VALTRD",
         "Attribute:MARKETPRICE3TRADESVALUE",
         "Attribute:ADMITTEDVALUE",
         "Attribute:WAVAL"
      },
      {
         "Attribute:BOARDID",
         "Attribute:TRADEDATE",
         "Attribute:SHORTNAME",
         "Attribute:SECID",
         "Attribute:NUMTRADES",
         "Attribute:VALUE",
         "Attribute:OPEN",
         "Attribute:LOW",
         "Attribute:HIGH",
         "Attribute:LEGALCLOSEPRICE",
         "Attribute:WAPRICE",
         "Attribute:CLOSE",
         "Attribute:VOLUME",
         "Attribute:MARKETPRICE2",
         "Attribute:MARKETPRICE3",
         "Attribute:ADMITTEDQUOTE",
         "Attribute:MP2VALTRD",
         "Attribute:MARKETPRICE3TRADESVALUE",
         "Attribute:ADMITTEDVALUE",
         "Attribute:WAVAL"
      }
   ),
   types = Table.TransformColumnNames(
      col_expand_table,
      each Text.AfterDelimiter(_, ":")
   ),
    #"Удаленные столбцы" = Table.RemoveColumns(types,{"BOARDID", "SHORTNAME", "SECID", "NUMTRADES", "VALUE", "OPEN", "LOW", "HIGH", "LEGALCLOSEPRICE", "WAPRICE", "VOLUME", "MARKETPRICE2", "MARKETPRICE3", "ADMITTEDQUOTE", "MP2VALTRD", "MARKETPRICE3TRADESVALUE", "ADMITTEDVALUE", "WAVAL"}),
    #"Сортированные строки" = Table.Sort(#"Удаленные столбцы",{{"TRADEDATE", Order.Descending}}),
    #"Измененный тип" = Table.TransformColumnTypes(#"Сортированные строки",{{"TRADEDATE", type date}}),
    #"Переименованные столбцы" = Table.RenameColumns(#"Измененный тип",{{"TRADEDATE", "Дата"}}),
    #"Замененное значение" = Table.ReplaceValue(#"Переименованные столбцы",".",",",Replacer.ReplaceText,{"CLOSE"}),
    #"Измененный тип1" = Table.TransformColumnTypes(#"Замененное значение",{{"CLOSE", type number}}),
    #"Переименованные столбцы1" = Table.RenameColumns(#"Измененный тип1",{{"CLOSE", "Масло"}})
in
    #"Переименованные столбцы1"
```

## ИПЦ н/н

```powerquery
let
  Источник = Json.Document(Web.Contents("https://m.bizon.ru/graph-ctl/rosstat_ipc_10297")),
    tables = Источник[tables],
    tables1 = tables{0},
    #"Преобразовано в таблицу" = Record.ToTable(tables1),
    #"Транспонированная таблица" = Table.Transpose(#"Преобразовано в таблицу"),
    #"Повышенные заголовки" = Table.PromoteHeaders(#"Транспонированная таблица", [PromoteAllScalars=true]),
    #"Измененный тип" = Table.TransformColumnTypes(#"Повышенные заголовки",{{"title", type text}, {"head", type any}, {"rows", type any}}),
    #"Развернутый элемент rows" = Table.ExpandListColumn(#"Измененный тип", "rows"),
    #"Развернутый элемент head" = Table.ExpandListColumn(#"Развернутый элемент rows", "head"),
    #"Удаленные столбцы" = Table.RemoveColumns(#"Развернутый элемент head",{"title"}),
    #"Несвернутые столбцы" = Table.UnpivotOtherColumns(#"Удаленные столбцы", {"head"}, "Атрибут", "Значение"),
    #"Извлеченные значения" = Table.TransformColumns(#"Несвернутые столбцы", {"Значение", each Text.Combine(List.Transform(_, Text.From), ","), type text}),
    #"Разделить столбец по положению" = Table.SplitColumn(#"Извлеченные значения", "Значение", Splitter.SplitTextByPositions({0, 10}, false), {"Значение.1", "Значение.2"}),
    #"Измененный тип1" = Table.TransformColumnTypes(#"Разделить столбец по положению",{{"Значение.1", type date}, {"Значение.2", type text}}),
    #"Разделить столбец по положению1" = Table.SplitColumn(#"Измененный тип1", "Значение.2", Splitter.SplitTextByPositions({0, 1}, false), {"Значение.2.1", "Значение.2.2"}),
    #"Измененный тип2" = Table.TransformColumnTypes(#"Разделить столбец по положению1",{{"Значение.2.1", type text}, {"Значение.2.2", type number}}),
    #"Удаленные дубликаты" = Table.Distinct(#"Измененный тип2", {"Значение.1"}),
    #"Удаленные столбцы1" = Table.RemoveColumns(#"Удаленные дубликаты",{"Значение.2.1"}),
    #"Сортированные строки" = Table.Sort(#"Удаленные столбцы1",{{"Значение.1", Order.Descending}}),
    #"Удаленные столбцы2" = Table.RemoveColumns(#"Сортированные строки",{"head", "Атрибут"}),
    #"Переименованные столбцы" = Table.RenameColumns(#"Удаленные столбцы2",{{"Значение.1", "Дата"}, {"Значение.2.2", "ИПЦ н/н"}})
in
    #"Переименованные столбцы"
```

## ИПЦ (к дек пг)

```powerquery
let
  Источник = Json.Document(Web.Contents("https://m.bizon.ru/graph-ctl/rosstat_ipc_10299")),
    tables = Источник[tables],
    tables1 = tables{0},
    #"Преобразовано в таблицу" = Record.ToTable(tables1),
    #"Повышенные заголовки" = Table.PromoteHeaders(#"Преобразовано в таблицу", [PromoteAllScalars=true]),
    #"Измененный тип" = Table.TransformColumnTypes(#"Повышенные заголовки",{{"title", type text}, {"Индекс потребительских цен (ИПЦ) (к декабрю прошлого года, недельные)", type any}}),
    #"Развернутый элемент Индекс потребительских цен (ИПЦ) (к декабрю прошлого года, недельные)" = Table.ExpandListColumn(#"Измененный тип", "Индекс потребительских цен (ИПЦ) (к декабрю прошлого года, недельные)"),
    #"Повышенные заголовки1" = Table.PromoteHeaders(#"Развернутый элемент Индекс потребительских цен (ИПЦ) (к декабрю прошлого года, недельные)", [PromoteAllScalars=true]),
    #"Измененный тип1" = Table.TransformColumnTypes(#"Повышенные заголовки1",{{"head", type text}, {"Дата", type any}}),
    #"Повышенные заголовки2" = Table.PromoteHeaders(#"Измененный тип1", [PromoteAllScalars=true]),
    #"Измененный тип2" = Table.TransformColumnTypes(#"Повышенные заголовки2",{{"head", type text}, {"Значение", type any}}),
    #"Извлеченные значения" = Table.TransformColumns(#"Измененный тип2", {"Значение", each Text.Combine(List.Transform(_, Text.From), " "), type text}),
    #"Разделить столбец по положению" = Table.SplitColumn(#"Извлеченные значения", "Значение", Splitter.SplitTextByPositions({0, 10}, false), {"Значение.1", "Значение.2"}),
    #"Измененный тип3" = Table.TransformColumnTypes(#"Разделить столбец по положению",{{"Значение.1", type date}, {"Значение.2", type number}}),
    #"Удаленные столбцы" = Table.RemoveColumns(#"Измененный тип3",{"head"}),
    #"Сортированные строки" = Table.Sort(#"Удаленные столбцы",{{"Значение.1", Order.Descending}}),
    #"Переименованные столбцы" = Table.RenameColumns(#"Сортированные строки",{{"Значение.1", "Дата"}, {"Значение.2", "ИПЦ к дек нг"}}),
    #"Дублированный столбец" = Table.DuplicateColumn(#"Переименованные столбцы", "Дата", "Копия Дата"),
    #"Измененный тип4" = Table.TransformColumnTypes(#"Дублированный столбец",{{"Копия Дата", type text}}),
    #"Переименованные столбцы1" = Table.RenameColumns(#"Измененный тип4",{{"Копия Дата", "Текст_Дата"}})
in
    #"Переименованные столбцы1"
```

## Hormuz

```powerquery
let
  Источник = Json.Document(Web.Contents("https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query?where=portname%20%3D%20'STRAIT%20OF%20HORMUZ'%20AND%20year%20%3E%3D%202025%20AND%20year%20%3C%3D%202027&outFields=*&outSR=4326&f=json")),
  #"Преобразовано в таблицу" = Table.FromRecords({Источник}),
  #"Развернуто: uniqueIdField" = Table.ExpandRecordColumn(#"Преобразовано в таблицу", "uniqueIdField", {"name", "isSystemMaintained"}, {"uniqueIdField.name", "uniqueIdField.isSystemMaintained"}),
  #"Измененный тип столбца" = Table.TransformColumnTypes(#"Развернуто: uniqueIdField", {{"objectIdFieldName", type text}, {"uniqueIdField.name", type text}, {"uniqueIdField.isSystemMaintained", type logical}, {"globalIdFieldName", type text}}, "ru"),
    #"Развернутый элемент features" = Table.ExpandListColumn(#"Измененный тип столбца", "features"),
    #"Развернутый элемент features1" = Table.ExpandRecordColumn(#"Развернутый элемент features", "features", {"attributes"}, {"features.attributes"}),
    #"Развернутый элемент features.attributes" = Table.ExpandRecordColumn(#"Развернутый элемент features1", "features.attributes", {"date", "year", "month", "day", "portid", "portname", "n_container", "n_dry_bulk", "n_general_cargo", "n_roro", "n_tanker", "n_cargo", "n_total", "capacity_container", "capacity_dry_bulk", "capacity_general_cargo", "capacity_roro", "capacity_tanker", "capacity_cargo", "capacity", "ObjectId"}, {"date", "year", "month", "day", "portid", "portname", "n_container", "n_dry_bulk", "n_general_cargo", "n_roro", "n_tanker", "n_cargo", "n_total", "capacity_container", "capacity_dry_bulk", "capacity_general_cargo", "capacity_roro", "capacity_tanker", "capacity_cargo", "capacity", "ObjectId"}),
    #"Удаленные столбцы" = Table.RemoveColumns(#"Развернутый элемент features.attributes",{"objectIdFieldName", "uniqueIdField.name", "uniqueIdField.isSystemMaintained", "globalIdFieldName", "fields"}),
    #"Измененный тип" = Table.TransformColumnTypes(#"Удаленные столбцы",{{"date", type date}, {"n_total", Int64.Type}, {"capacity_container", Int64.Type}, {"capacity_dry_bulk", Int64.Type}, {"capacity_general_cargo", Int64.Type}, {"capacity_roro", Int64.Type}, {"capacity_tanker", Int64.Type}, {"capacity_cargo", Int64.Type}, {"capacity", Int64.Type}, {"n_container", Int64.Type}, {"n_dry_bulk", Int64.Type}, {"n_general_cargo", Int64.Type}, {"n_roro", Int64.Type}, {"n_tanker", Int64.Type}, {"n_cargo", Int64.Type}}),
    #"Сортированные строки" = Table.Sort(#"Измененный тип",{{"date", Order.Descending}}),
    #"Несвернутые столбцы" = Table.UnpivotOtherColumns(#"Сортированные строки", {"date", "year", "month", "day", "portid", "portname", "n_cargo", "n_total", "capacity_container", "capacity_dry_bulk", "capacity_general_cargo", "capacity_roro", "capacity_tanker", "capacity_cargo", "capacity", "ObjectId"}, "Атрибут", "Значение"),
    #"Замененное значение" = Table.ReplaceValue(#"Несвернутые столбцы","n_container","Контейнеровозы",Replacer.ReplaceText,{"Атрибут"}),
    #"Замененное значение1" = Table.ReplaceValue(#"Замененное значение","n_dry_bulk","Балкеры",Replacer.ReplaceText,{"Атрибут"}),
    #"Замененное значение2" = Table.ReplaceValue(#"Замененное значение1","n_general_cargo","Сухогрузы",Replacer.ReplaceText,{"Атрибут"}),
    #"Замененное значение3" = Table.ReplaceValue(#"Замененное значение2","n_roro","Суда для накатных грузов",Replacer.ReplaceText,{"Атрибут"}),
    #"Замененное значение4" = Table.ReplaceValue(#"Замененное значение3","n_tanker","Танкеры",Replacer.ReplaceText,{"Атрибут"}),
    #"Строки с примененным фильтром" = Table.SelectRows(#"Замененное значение4", each true)
in
  #"Строки с примененным фильтром"
```

---

## Дополнительные валютные ряды HTML-версии

Эти ряды отсутствовали в исходном PBIX и добавлены непосредственно в HTML-приложение.

### EUR/RUB

- источник: официальный XML-сервис динамики курсов ЦБ РФ;
- код валютного ряда: `R01239`;
- адрес: `https://www.cbr.ru/scripts/XML_dynamic.asp`;
- итоговый показатель: рублей за 1 EUR.

### CNY/RUB

- источник: официальный XML-сервис динамики курсов ЦБ РФ;
- код валютного ряда: `R01375`;
- адрес: `https://www.cbr.ru/scripts/XML_dynamic.asp`;
- итоговый показатель: рублей за 1 CNY;
- значение XML делится на поле `Nominal`, поэтому корректно обрабатываются периоды, когда ЦБ РФ публикует котировку за несколько единиц валюты.
