// SPIDER - step 4: export every link the code property graph holds.
//
// Joern is told which graph to open and where to write through two environment
// variables, because this Joern release accepts --param only as a flag and
// never carries a value:
//
//     SPIDER_CPG   the .cpg.bin file to open
//     SPIDER_OUT   the .tsv file to write
//
// One line of the output is one link, twelve columns:
//
//     kind, then for each end: file, line, enclosing method, node label,
//     node code (cleaned of tabs and newlines), and last the variable a
//     data-flow edge carries.
//
// The five extra columns per end exist so that the merge can judge a link
// by the graph's own record - what KIND of node an edge lands on, inside
// which function it stands, what its code says - instead of judging it by
// derived guesses. Nothing is chosen and nothing is thrown away here: every
// kind of link the graph holds is written down, and what to do with each of
// them is decided later, against the statement list.

@main def exec() = {
  val cpgFile = sys.env.getOrElse("SPIDER_CPG", "")
  val outFile = sys.env.getOrElse("SPIDER_OUT", "")
  if (cpgFile.isEmpty || outFile.isEmpty) {
    println("SPIDER_ERROR set SPIDER_CPG and SPIDER_OUT before running")
  } else {
    importCpg(cpgFile)
    def clean(value: String): String =
      value.replace('\\', '/').replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')

    // The AST parents, so every node can name its enclosing method.
    println("SPIDER_STAGE building the parent and method maps")
    val astParent = scala.collection.mutable.LongMap[Long]()
    val methodNames = scala.collection.mutable.LongMap[String]()
    cpg.all.foreach { node =>
      node match {
        case method: nodes.Method => methodNames.update(method.id(), clean(method.fullName))
        case _ => ()
      }
      node.outE.foreach { edge =>
        if (edge.label == "AST") astParent.update(edge.dst.id(), node.id())
      }
    }
    def enclosingMethod(id: Long): String = {
      var current = id
      var hops = 0
      while (hops < 10000) {
        methodNames.get(current) match {
          case Some(value) => return value
          case None => ()
        }
        astParent.get(current) match {
          case Some(value) => current = value
          case None => return ""
        }
        hops += 1
      }
      ""
    }

    // The address of a node is looked up once and remembered, because the same
    // node is the end of many links and the lookup walks the graph every time.
    println("SPIDER_STAGE building the address map")
    val address =
      scala.collection.mutable.LongMap[(String, String, String, String, String)]()
    cpg.all.foreach {
      case node: nodes.AstNode =>
        val file = clean(node.file.name.headOption.getOrElse(""))
        val line = node.lineNumber.map(_.toString).getOrElse("")
        val method = enclosingMethod(node.id())
        val label = clean(node.label)
        val code = clean(node.code).take(120)
        if (file.nonEmpty || line.nonEmpty)
          address.update(node.id(), (file, line, method, label, code))
      case _ => ()
    }
    println("SPIDER_ADDRESSES " + address.size)

    val writer = new java.io.PrintWriter(new java.io.BufferedWriter(
      new java.io.OutputStreamWriter(new java.io.FileOutputStream(outFile),
        java.nio.charset.StandardCharsets.UTF_8), 1 << 20))

    var written = 0L
    val counts = scala.collection.mutable.Map[String, Long]()

    cpg.all.foreach { from =>
      val (fromFile, fromLine, fromMethod, fromLabel, fromCode) =
        address.getOrElse(from.id(), ("", "", "", "", ""))
      from.outE.foreach { edge =>
        val (toFile, toLine, toMethod, toLabel, toCode) =
          address.getOrElse(edge.dst.id(), ("", "", "", "", ""))
        val kind = edge.label
        val variable = edge match {
          case reaching: edges.ReachingDef =>
            clean(reaching.propertyMaybe.map(_.toString).getOrElse(""))
          case _ => ""
        }
        writer.println(
          s"$kind\t$fromFile\t$fromLine\t$fromMethod\t$fromLabel\t$fromCode" +
          s"\t$toFile\t$toLine\t$toMethod\t$toLabel\t$toCode\t$variable")
        written += 1
        counts(kind) = counts.getOrElse(kind, 0L) + 1
      }
    }

    writer.close()
    println("SPIDER_WRITTEN " + written)
    counts.toList.sortBy(-_._2).foreach { case (k, v) =>
      println("SPIDER_KIND\t" + k + "\t" + v)
    }
  }
}
