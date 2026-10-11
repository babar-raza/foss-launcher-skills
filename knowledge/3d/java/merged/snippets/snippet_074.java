import com.aspose.threed.CurveDimension;
import com.aspose.threed.NurbsCurve;
import com.aspose.threed.NurbsType;

NurbsCurve curve = new NurbsCurve();
curve.setOrder(4);
System.out.println(curve.getDegree());
System.out.println(curve.getDimension());
System.out.println(curve.getCurveType());
